import os
import sqlite3
import json
import time
import concurrent.futures
from google import genai
from google.genai import types
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
RULES_PATH = "gemini_extraction_rules.md"
MAX_WORKERS = 2  

# Initialize the new SDK Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# The new SDK drops the "models/" prefix 
MODEL_NAME = "gemini-2.5-flash"

# --- 2. HELPER FUNCTIONS ---
def upload_to_gemini(path, mime_type=None, max_retries=3):
    """Uploads the file to Gemini's File API using the new SDK."""
    for attempt in range(max_retries):
        try:
            file = client.files.upload(
                file=path,
                config=types.UploadFileConfig(mime_type=mime_type)
            )
            return file
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt + 1} failed for {os.path.basename(path)}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1)) 
            else:
                return None

def wait_for_files_active(gemini_file):
    """Waits for Gemini to finish parsing the PDF on their end."""
    file = client.files.get(name=gemini_file.name)
    while file.state.name == "PROCESSING":
        time.sleep(2)
        file = client.files.get(name=gemini_file.name)
    if file.state.name != "ACTIVE":
        raise Exception(f"File {file.name} failed to process.")

# --- 3. THE WORKER THREAD ---
def process_pdf_file(file_data, extraction_rules):
    file_id, filename, staged_path = file_data
    
    if not os.path.exists(staged_path):
        return {'id': file_id, 'status': 'ERROR_NOT_FOUND'}

    gemini_file = None
    try:
        # 1. Upload the PDF
        gemini_file = upload_to_gemini(staged_path, mime_type="application/pdf")
        if not gemini_file:
             return {'id': file_id, 'status': 'API_ERROR', 'error': 'Upload failed', 'filename': filename}
        
        wait_for_files_active(gemini_file)

        # 2. Call the AI using the new SDK syntax
        user_prompt = f"File Metadata:\nFilename: {filename}\nPath: {staged_path}\n\nPlease extract the semantic blocks based on the rules."
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[gemini_file, user_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=extraction_rules
            )
        )
        
        ai_data = json.loads(response.text)
        
        # 3. Clean up metadata variables for prepending
        est_year = ai_data.get("Estimated_Year", "Unknown")
        client_name = ai_data.get("Company_or_Client", "Unknown")
        raw_blocks = ai_data.get("Semantic_Blocks", [])

        final_blocks = []
        for block in raw_blocks:
            prepended_block = f"[File: {filename} | Path: {staged_path} | Client: {client_name} | Year: {est_year}]\n{block}"
            final_blocks.append(prepended_block)

        return {'id': file_id, 'status': 'COMPLETED_GEMINI', 'blocks': final_blocks, 'filename': filename}
                    
    except Exception as e:
        return {'id': file_id, 'status': 'API_ERROR', 'error': str(e), 'filename': filename}
    finally:
        time.sleep(3) # Metronome pause
        # 4. ALWAYS delete the file from Google's servers
        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
            except:
                pass

# --- 4. MAIN ORCHESTRATOR ---
def run_extractor():
    if not os.path.exists(RULES_PATH):
        print(f"❌ Error: {RULES_PATH} not found.")
        return

    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        extraction_rules = f.read()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Grab approved PDFs designated for Gemini
    cursor.execute('''
        SELECT id, filename, staged_path 
        FROM manifest 
        WHERE status = 'APPROVED_FOR_EXTRACTION' 
        AND route = 'ROUTE_GEMINI_MULTIMODAL'
        AND extension = '.pdf'
    ''')
    files = cursor.fetchall()
    
    if not files:
        print("No Gemini-eligible PDFs pending extraction.")
        conn.close()
        return

    print(f"🚀 Loaded {len(files)} PDFs for Gemini Semantic Extraction.")
    print(f"Igniting {MAX_WORKERS} worker threads...\n")

    processed_count = 0
    total_blocks_generated = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(process_pdf_file, f, extraction_rules): f for f in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            result = future.result()
            file_id = result['id']
            status = result['status']
            filename = result.get('filename', 'Unknown')
            
            if status == 'API_ERROR':
                print(f"⚠️ API Error on {filename}: {result.get('error')}")
                continue
            
            blocks = result.get('blocks', [])
            
            if status == 'COMPLETED_GEMINI':
                # Write to database
                for block_text in blocks:
                    cursor.execute('''
                        INSERT INTO semantic_blocks (manifest_id, block_text)
                        VALUES (?, ?)
                    ''', (file_id, block_text))
                
                cursor.execute('''
                    UPDATE manifest 
                    SET status = 'COMPLETED_GEMINI'
                    WHERE id = ?
                ''', (file_id,))
                
                print(f"✅ Extracted {len(blocks)} blocks from PDF: {filename}")
                total_blocks_generated += len(blocks)

            conn.commit()
            processed_count += 1
            
            if processed_count % 10 == 0:
                print(f"\n--- Processed {processed_count}/{len(files)} PDFs | Total Blocks: {total_blocks_generated} ---\n")

    conn.close()
    print("\n🏁 --- GEMINI EXTRACTION COMPLETE --- 🏁")
    print(f"Total PDF Blocks Ready for Vectorization: {total_blocks_generated}")

if __name__ == "__main__":
    run_extractor()