import os
import json
import sqlite3
import re
import concurrent.futures
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
DROP_DIR = os.path.join(STAGING_DIR, "custom_drops")
RULES_PATH = "email_extraction_rules.md"
TARGETS_PATH = "email_assassin_targets.txt"
MAX_WORKERS = 5 

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)
MODEL_NAME = "deepseek-chat" 

# --- 2. PRE-PROCESSING HELPERS ---
def load_email_assassins():
    """Reads the copied report lines and extracts just the target names/emails."""
    if not os.path.exists(TARGETS_PATH):
        print(f"⚠️ {TARGETS_PATH} not found. Running without a kill list.")
        return set()
        
    targets = set()
    with open(TARGETS_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if '->' in line:
                target = line.split('->')[-1].strip().lower()
                if target:
                    targets.add(target)
    return targets

def clean_email_body(body_text):
    """Strips forwards, HTML, and noise from the email body."""
    if not isinstance(body_text, str):
        return ""
        
    # Sever the text at the first sign of a reply chain or forward
    body_text = re.split(r'-----Original Message-----|From:|On .* wrote:', body_text, flags=re.IGNORECASE)[0]
    
    # Strip lingering HTML tags just in case
    body_text = re.sub(r'<[^>]+>', ' ', body_text)
    return body_text.strip()

# --- 3. THE WORKER THREAD ---
def process_single_email(job_data, extraction_rules):
    """Sends the packaged email to DeepSeek for analysis."""
    email_package = job_data['text']
    file_name = job_data['file_name']
    year = job_data['year']
    collaborator = job_data['to']
    subject = job_data['subj']
    job_id = job_data['id']
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": extraction_rules},
                {"role": "user", "content": email_package}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Smart Bouncer: Drop it if the AI says it's not career IP
        if not result.get("Is_Valid_Career_Data"):
            return {'id': job_id, 'status': 'SKIPPED', 'blocks': []}
            
        raw_blocks = result.get("Semantic_Blocks", [])
        final_blocks = []
        
        # Tag the data with the explicit Sent_Email category and Subject line
        for block in raw_blocks:
            final_blocks.append(f"[Category: Sent_Email | Subject: {subject} | Collaborator: {collaborator} | Year: {year}]\n{block}")
            
        return {'id': job_id, 'status': 'COMPLETED', 'blocks': final_blocks}
        
    except Exception as e:
        return {'id': job_id, 'status': 'API_ERROR', 'error': str(e)}

# --- 4. MAIN ORCHESTRATOR ---
def run_email_parser():
    # Load rules and targets
    if not os.path.exists(RULES_PATH):
        print(f"❌ Error: {RULES_PATH} not found.")
        return
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        extraction_rules = f.read()

    kill_list = load_email_assassins()
    print(f"🛡️ Loaded {len(kill_list)} targets into the Email Assassin.")

    # Locate CSV
    csv_files = [f for f in os.listdir(DROP_DIR) if f.endswith('.csv')]
    if not csv_files:
        print(f"⚠️ No CSV files found in {DROP_DIR}.")
        return

    csv_name = csv_files[0]
    csv_path = os.path.join(DROP_DIR, csv_name)
    
    print(f"🚀 Opening {csv_name}...")

    # Load Data (with encoding fallback)
    try:
        df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip', low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding='cp1252', on_bad_lines='skip', low_memory=False)

    # Detect Columns (PRIORITIZING YOUR EXACT HEADERS)
    to_col = next((c for c in ['DisplayTo', 'To', 'Recipient'] if c in df.columns), None)
    subj_col = next((c for c in ['Subject', 'Title'] if c in df.columns), None)
    body_col = next((c for c in ['Body.Text', 'Body.TextBody', 'Body', 'Content', 'Preview'] if c in df.columns), None)
    date_col = next((c for c in ['DateTimeSent', 'DateTime', 'Date', 'Sent'] if c in df.columns), None)

    if not all([to_col, subj_col, body_col, date_col]):
        print(f"❌ Missing required columns. Found: {list(df.columns)}")
        return

    # Phase 1: Local Pre-processing (The Guillotine)
    valid_jobs = []
    job_counter = 0

    df = df.fillna('') # Replace NaN with empty strings

    # FIX: Use iterrows() to treat rows like a dictionary and bypass the dot-notation rule!
    for index, row in df.iterrows():
        to_val = str(row[to_col]).strip()
        subj_val = str(row[subj_col]).strip()
        body_val = str(row[body_col]).strip()
        date_val = str(row[date_col]).strip()

        # Trap 1: Assassin check
        if to_val.lower() in kill_list or not to_val:
            continue

        # Trap 2: Clean the body
        clean_body = clean_email_body(body_val)
        
        # Trap 3: Length Guillotine (Drop anything under 15 words)
        if len(clean_body.split()) < 15:
            continue

        # Extract Year
        year = date_val[:4] if len(date_val) >= 4 else "Unknown"

        # Package it up
        email_package = f"Date: {date_val}\nTo: {to_val}\nSubject: {subj_val}\nBody:\n{clean_body}"
        
        job_counter += 1
        valid_jobs.append({
            'id': job_counter, 
            'text': email_package, 
            'file_name': csv_name,
            'to': to_val,
            'subj': subj_val,
            'year': year
        })

    print(f"✂️ Local filtering complete. Kept {len(valid_jobs)} substantive emails out of {len(df)} total rows.")
    if not valid_jobs:
        return

    print(f"Igniting {MAX_WORKERS} worker threads for DeepSeek extraction...\n")

    # Phase 2: Threaded API Extraction
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total_blocks_saved = 0
    processed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(process_single_email, job, extraction_rules): job for job in valid_jobs}
        
        for future in concurrent.futures.as_completed(future_to_job):
            result = future.result()
            status = result['status']
            
            if status == 'API_ERROR':
                print(f"⚠️ API Error on Job {result['id']}: {result.get('error')}")
            elif status == 'COMPLETED':
                blocks = result.get('blocks', [])
                if blocks:
                    for block_text in blocks:
                        cursor.execute('''
                            INSERT INTO semantic_blocks (manifest_id, block_text)
                            VALUES (?, ?)
                        ''', (None, block_text))
                    
                    conn.commit()
                    total_blocks_saved += len(blocks)
            
            processed_count += 1
            if processed_count % 100 == 0:
                print(f"--- Processed {processed_count}/{len(valid_jobs)} emails | Total Strategy Blocks: {total_blocks_saved} ---")

    conn.close()
    print(f"\n🏁 --- EMAIL EXTRACTION COMPLETE --- 🏁")
    print(f"Total Sent Email Blocks Secured: {total_blocks_saved}")

if __name__ == "__main__":
    run_email_parser()