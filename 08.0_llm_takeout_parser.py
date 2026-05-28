import os
import json
import sqlite3
import re
import concurrent.futures
from openai import OpenAI
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
DROP_DIR = os.path.join(STAGING_DIR, "custom_drops") # Ensuring safe pathing
RULES_PATH = "llm_extraction_rules.md"
MAX_WORKERS = 5

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)
MODEL_NAME = "deepseek-chat"

# --- 2. THE WORKER THREAD ---
def process_single_interaction(job_data, extraction_rules):
    """Worker thread that ONLY handles the API call, no database writes."""
    interaction_text = job_data['text']
    file_name = job_data['file_name']
    year = job_data['year']
    job_id = job_data['id']
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": extraction_rules},
                {"role": "user", "content": interaction_text}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if not result.get("Is_Valid_Strategy"):
            return {'id': job_id, 'status': 'SKIPPED', 'blocks': []}
            
        raw_blocks = result.get("Semantic_Blocks", [])
        final_blocks = []
        
        for block in raw_blocks:
            final_blocks.append(f"[Category: AI_Chat_Log | File: {file_name} | Year: {year}]\n{block}")
            
        return {'id': job_id, 'status': 'COMPLETED', 'blocks': final_blocks}
        
    except Exception as e:
        return {'id': job_id, 'status': 'API_ERROR', 'error': str(e)}

# --- 3. MAIN ORCHESTRATOR ---
def run_parser():
    if not os.path.exists(RULES_PATH):
        print(f"❌ Error: {RULES_PATH} not found.")
        return
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        extraction_rules = f.read()

    if not os.path.exists(DROP_DIR):
        print(f"❌ Error: Folder '{DROP_DIR}' not found.")
        return
        
    json_files = [f for f in os.listdir(DROP_DIR) if f.endswith('.json')]
    if not json_files:
        print(f"⚠️ No JSON files found in {DROP_DIR}.")
        return

    print(f"🚀 Found {len(json_files)} Takeout file(s). Pre-processing data locally...")

    # Phase 1: Local Pre-processing (The Guillotine)
    valid_jobs = []
    job_counter = 0

    for file_name in json_files:
        file_path = os.path.join(DROP_DIR, file_name)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        for item in data:
            time_str = item.get("time", "Unknown")
            year = time_str[:4] if len(time_str) >= 4 else "Unknown"

            user_prompt = item.get("title", "")
            if user_prompt.startswith("Prompted "):
                user_prompt = user_prompt.replace("Prompted ", "", 1)
            
            ai_response_html = ""
            safe_html_list = item.get("safeHtmlItem", [])
            if safe_html_list and isinstance(safe_html_list, list):
                ai_response_html = safe_html_list[0].get("html", "")
                
            if not user_prompt or not ai_response_html:
                continue

            cleaned_ai = re.sub(r'<pre><code.*?>.*?</code></pre>', '\n[CODE/QUERY REMOVED]\n', ai_response_html, flags=re.DOTALL|re.IGNORECASE)
            cleaned_ai = re.sub(r'<[^>]+>', '', cleaned_ai)
            cleaned_ai = cleaned_ai.replace("&#39;", "'").replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<")

            if len(cleaned_ai.split()) < 40:
                continue
                
            interaction_text = f"User: {user_prompt}\n\nAI: {cleaned_ai}"
            job_counter += 1
            valid_jobs.append({
                'id': job_counter, 
                'text': interaction_text, 
                'file_name': file_name, 
                'year': year
            })

    print(f"✂️ Local filtering complete. Kept {len(valid_jobs)} substantive interactions.")
    if not valid_jobs:
        return

    print(f"Igniting {MAX_WORKERS} worker threads for DeepSeek extraction...\n")

    # Phase 2: Threaded API Extraction & Database Injection
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    total_blocks_saved = 0
    processed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_job = {executor.submit(process_single_interaction, job, extraction_rules): job for job in valid_jobs}
        
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
                        ''', (None, block_text)) # None because these are custom drops
                    
                    conn.commit()
                    total_blocks_saved += len(blocks)
            
            processed_count += 1
            if processed_count % 100 == 0:
                print(f"--- Processed {processed_count}/{len(valid_jobs)} interactions | Total AI Blocks: {total_blocks_saved} ---")

    conn.close()
    print(f"\n🏁 --- TAKEOUT EXTRACTION COMPLETE --- 🏁")
    print(f"Total AI Strategy Blocks Secured: {total_blocks_saved}")

if __name__ == "__main__":
    run_parser()