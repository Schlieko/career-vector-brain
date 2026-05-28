import os
import shutil
import sqlite3
import json
import fitz  # PyMuPDF for standard PDFs
import docx  # python-docx for Word files
import concurrent.futures
from openai import OpenAI
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
REJECTED_DIR = os.path.join(STAGING_DIR, "_Vector_Rejected")
RULES_PATH = "triage_rules.md"
MAX_WORKERS = 10 # <-- THE TURBOCHARGER: Processes 10 files at the exact same time

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), 
    base_url="https://api.deepseek.com"
)

# --- 2. HELPER FUNCTIONS ---
def setup_database_updates(cursor):
    try:
        cursor.execute("ALTER TABLE manifest ADD COLUMN ai_classification TEXT")
        cursor.execute("ALTER TABLE manifest ADD COLUMN ai_reason TEXT")
    except sqlite3.OperationalError:
        pass 

def get_text_snippet(filepath, ext, max_chars=1500):
    snippet = ""
    try:
        if ext == '.pdf':
            doc = fitz.open(filepath)
            for page in doc[:2]: 
                snippet += page.get_text() + "\n"
            doc.close()
        elif ext in ['.docx', '.doc']:
            doc = docx.Document(filepath)
            snippet = "\n".join([p.text for p in doc.paragraphs[:20]])
        else:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                snippet = f.read(max_chars)
    except Exception as e:
        return f"[Error extracting text: {e}]"
    return snippet[:max_chars].strip()

def move_to_quarantine(staged_path):
    rel_path = os.path.relpath(staged_path, STAGING_DIR)
    quarantine_path = os.path.join(REJECTED_DIR, rel_path)
    os.makedirs(os.path.dirname(quarantine_path), exist_ok=True)
    shutil.move(staged_path, quarantine_path)
    return quarantine_path

# --- 3. THE WORKER THREAD (No Database Access Here!) ---
def process_single_file(file_data, constitution):
    file_id, filename, ext, staged_path, size_bytes = file_data
    
    if not os.path.exists(staged_path):
        return {'id': file_id, 'status': 'ERROR_NOT_FOUND', 'filename': filename}

    # Pre-Flight
    if ext in ['.sql', '.json', '.csv'] and size_bytes < 5000:
        new_path = move_to_quarantine(staged_path)
        return {'id': file_id, 'status': 'REJECTED_SIZE_THRESHOLD', 'path': new_path, 
                'class': 'Auto', 'reason': 'Pre-flight: File under 5KB', 'filename': filename}

    # Extract
    snippet = get_text_snippet(staged_path, ext)
    if not snippet:
        new_path = move_to_quarantine(staged_path)
        return {'id': file_id, 'status': 'REJECTED_EMPTY', 'path': new_path, 
                'class': 'Auto', 'reason': 'No readable text', 'filename': filename}

    # API Call
    system_prompt = f"{constitution}\n\nYou must return strictly a JSON object with keys: 'Classification', 'Vectorize' (boolean), and 'Reason'."
    user_prompt = f"File Metadata:\nFilename: {filename}\nPath: {staged_path}\n\nFile Snippet:\n{snippet}"

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={'type': 'json_object'}
        )
        
        ai_data = json.loads(response.choices[0].message.content)
        should_vectorize = ai_data.get("Vectorize", False)
        classification = ai_data.get("Classification", "Unknown")
        reason = ai_data.get("Reason", "No reason provided")

        if should_vectorize:
            return {'id': file_id, 'status': 'APPROVED_FOR_EXTRACTION', 'path': staged_path, 
                    'class': classification, 'reason': reason, 'filename': filename}
        else:
            new_path = move_to_quarantine(staged_path)
            return {'id': file_id, 'status': 'REJECTED_BY_AI', 'path': new_path, 
                    'class': classification, 'reason': reason, 'filename': filename}
                    
    except Exception as e:
        return {'id': file_id, 'status': 'API_ERROR', 'error': str(e), 'filename': filename}

# --- 4. MAIN ORCHESTRATOR ---
def run_triage():
    if not os.path.exists(RULES_PATH):
        print(f"❌ Error: {RULES_PATH} not found.")
        return

    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        constitution = f.read()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    setup_database_updates(cursor)

    # Grab pending files (INCLUDING PDFs!)
    cursor.execute('''
        SELECT id, filename, extension, staged_path, size_bytes 
        FROM manifest 
        WHERE status = 'PENDING_AI' 
        AND (route = 'ROUTE_DEEPSEEK_TEXT' OR extension = '.pdf')
    ''')
    files = cursor.fetchall()
    
    if not files:
        print("No files pending AI triage.")
        return

    print(f"🚀 Loaded {len(files)} files. Igniting {MAX_WORKERS} worker threads...\n")

    processed_count = 0

    # The Thread Pool Executor
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all jobs to the pool
        future_to_file = {executor.submit(process_single_file, f, constitution): f for f in files}
        
        # As each thread finishes its API call, process the result one by one (Database safe!)
        for future in concurrent.futures.as_completed(future_to_file):
            result = future.result()
            file_id = result['id']
            status = result['status']
            filename = result['filename']
            
            if status == 'API_ERROR':
                print(f"⚠️ API Error on {filename}: {result.get('error')}")
                continue
            elif status == 'ERROR_NOT_FOUND':
                continue
                
            class_name = result.get('class', '')
            reason = result.get('reason', '')
            path = result.get('path', '')

            if 'APPROVED' in status:
                cursor.execute('''
                    UPDATE manifest 
                    SET status = ?, ai_classification = ?, ai_reason = ?
                    WHERE id = ?
                ''', (status, class_name, reason, file_id))
                print(f"✅ Approved: {filename} [{class_name}]")
            else:
                cursor.execute('''
                    UPDATE manifest 
                    SET status = ?, staged_path = ?, ai_classification = ?, ai_reason = ?
                    WHERE id = ?
                ''', (status, path, class_name, reason, file_id))
                if 'SIZE' in status:
                     print(f"🚫 Rejected (Size): {filename}")
                else:
                     print(f"🤖 AI Rejected: {filename} [{class_name}]")

            conn.commit()
            processed_count += 1
            
            # Quick status update every 100 files
            if processed_count % 100 == 0:
                print(f"\n--- Processed {processed_count}/{len(files)} files ---\n")

    conn.close()
    print("\n🏁 --- TRIAGE COMPLETE --- 🏁")
    print(f"Review rejected files in: {REJECTED_DIR}")

if __name__ == "__main__":
    run_triage()