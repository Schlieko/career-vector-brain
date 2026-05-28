import os
import sqlite3
import json
import docx
import concurrent.futures
from openai import OpenAI
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
RULES_PATH = "deepseek_extraction_rules.md"
MAX_WORKERS = 10 

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), 
    base_url="https://api.deepseek.com"
)

# --- 2. HELPER FUNCTIONS ---
def setup_blocks_table(cursor):
    """Creates a dedicated table to store the final vector chunks."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semantic_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manifest_id INTEGER,
            block_text TEXT,
            FOREIGN KEY(manifest_id) REFERENCES manifest(id)
        )
    ''')

def get_full_text(filepath, ext):
    """Reads the entire document for deep extraction."""
    text = ""
    try:
        # python-docx CANNOT read legacy .doc files, only .docx
        if ext == '.docx':
            doc = docx.Document(filepath)
            text = "\n".join([p.text for p in doc.paragraphs])
        elif ext == '.doc':
            print(f"⚠️ Skipping legacy .doc file (requires conversion): {filepath}")
            return None
        else:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except Exception as e:
        print(f"⚠️ Failed to read {filepath}: {e}")
        return None # Return None instead of the error string!
    
    # Cap at 80,000 characters (~20,000 tokens)
    if not text or not text.strip():
        return None
        
    return text[:80000].strip()

# --- 3. THE WORKER THREAD ---
def extract_blocks_from_file(file_data, extraction_rules):
    file_id, filename, ext, staged_path = file_data
    
    if not os.path.exists(staged_path):
        return {'id': file_id, 'status': 'ERROR_NOT_FOUND', 'blocks': []}

    full_text = get_full_text(staged_path, ext)
    if not full_text:
        return {'id': file_id, 'status': 'ERROR_EMPTY_OR_SKIPPED', 'blocks': []}

    system_prompt = extraction_rules
    user_prompt = f"File Metadata:\nFilename: {filename}\nPath: {staged_path}\n\nDocument Text:\n{full_text}"

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash", # <--- NEW CHEAPER MODEL
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={'type': 'json_object'}
        )
        
        ai_data = json.loads(response.choices[0].message.content)
        
        # Clean up metadata variables for prepending
        est_year = ai_data.get("Estimated_Year", "Unknown")
        client_name = ai_data.get("Company_or_Client", "Unknown")
        raw_blocks = ai_data.get("Semantic_Blocks", [])

        # Create the final, metadata-rich string for LanceDB
        final_blocks = []
        for block in raw_blocks:
            prepended_block = f"[File: {filename} | Path: {staged_path} | Client: {client_name} | Year: {est_year}]\n{block}"
            final_blocks.append(prepended_block)

        return {'id': file_id, 'status': 'COMPLETED_DEEPSEEK', 'blocks': final_blocks, 'filename': filename}
                    
    except Exception as e:
        return {'id': file_id, 'status': 'API_ERROR', 'error': str(e), 'filename': filename}

# --- 4. MAIN ORCHESTRATOR ---
def run_extractor():
    if not os.path.exists(RULES_PATH):
        print(f"❌ Error: {RULES_PATH} not found.")
        return

    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        extraction_rules = f.read()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    setup_blocks_table(cursor)

    # Grab approved TEXT files only (Ignores custom_drops folder)
    cursor.execute('''
        SELECT id, filename, extension, staged_path 
        FROM manifest 
        WHERE status = 'APPROVED_FOR_EXTRACTION' 
        AND route = 'ROUTE_DEEPSEEK_TEXT'
        AND staged_path NOT LIKE '%custom_drops%'
    ''')
    files = cursor.fetchall()
    
    if not files:
        print("No DeepSeek-eligible files pending extraction.")
        return

    print(f"🚀 Loaded {len(files)} files for Semantic Extraction.")
    print(f"Igniting {MAX_WORKERS} worker threads...\n")

    processed_count = 0
    total_blocks_generated = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_file = {executor.submit(extract_blocks_from_file, f, extraction_rules): f for f in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            result = future.result()
            file_id = result['id']
            status = result['status']
            filename = result.get('filename', 'Unknown')
            
            if status == 'API_ERROR':
                print(f"⚠️ API Error on {filename}: {result.get('error')}")
                continue
            elif status == 'ERROR_EMPTY_OR_SKIPPED':
                continue # Soft skip for things like legacy .doc files
            
            blocks = result.get('blocks', [])
            
            if status == 'COMPLETED_DEEPSEEK':
                # 1. Save all generated blocks to the new table
                for block_text in blocks:
                    cursor.execute('''
                        INSERT INTO semantic_blocks (manifest_id, block_text)
                        VALUES (?, ?)
                    ''', (file_id, block_text))
                
                # 2. Update the master manifest status
                cursor.execute('''
                    UPDATE manifest 
                    SET status = 'COMPLETED_DEEPSEEK'
                    WHERE id = ?
                ''', (file_id,))
                
                print(f"✅ Extracted {len(blocks)} blocks from: {filename}")
                total_blocks_generated += len(blocks)

            conn.commit()
            processed_count += 1
            
            if processed_count % 50 == 0:
                print(f"\n--- Processed {processed_count}/{len(files)} files | Total Blocks: {total_blocks_generated} ---\n")

    conn.close()
    print("\n🏁 --- DEEPSEEK EXTRACTION COMPLETE --- 🏁")
    print(f"Total Semantic Blocks Ready for Vectorization: {total_blocks_generated}")

if __name__ == "__main__":
    run_extractor()