import os
import shutil
import hashlib
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
SOURCE_DIR = os.getenv("SOURCE_DIR")
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
EXTENSIONS_FILE = "target_extensions.txt"

# --- 2. HELPER FUNCTIONS ---
def load_target_extensions():
    """Dynamically loads allowed extensions from the text file."""
    if not os.path.exists(EXTENSIONS_FILE):
        print(f"❌ Error: {EXTENSIONS_FILE} not found!")
        return set()
    
    exts = set()
    with open(EXTENSIONS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            clean = line.strip().lower()
            if clean and not clean.startswith('#'):
                # Ensure it starts with a dot
                if not clean.startswith('.'):
                    clean = '.' + clean
                exts.add(clean)
    return exts

def get_file_hash(filepath):
    """Generates MD5 hash in chunks."""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return "ERROR_UNREADABLE"

def setup_database():
    """Initializes the SQLite Manifest Database with rich metadata."""
    os.makedirs(STAGING_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT,
            staged_path TEXT,
            filename TEXT,
            extension TEXT,
            hash TEXT UNIQUE,
            size_bytes INTEGER,
            created_date TEXT,
            modified_date TEXT,
            route TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    return conn

# --- 3. MAIN ETL PIPELINE ---
def build_manifest():
    target_exts = load_target_extensions()
    if not target_exts:
        return

    conn = setup_database()
    cursor = conn.cursor()
    
    seen_hashes = set()
    processed_count = 0
    copied_count = 0
    
    print(f"Starting ETL Pipeline from {SOURCE_DIR}...")
    print(f"Tracking {len(target_exts)} extensions. Extracting, Version-Controlling, and Staging...\n")
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        
        # 1. First Pass: Group by base name and find the latest version
        valid_files = [f for f in files if os.path.splitext(f)[1].lower() in target_exts]
        if not valid_files:
            continue
            
        latest_files_group = {}
        for filename in valid_files:
            name_no_ext = os.path.splitext(filename)[0]
            fn_lower = filename.lower()
            
            # Version strip regex (This is your draft control logic!)
            base_name = re.sub(r'[\s\-_]+[vV]?[\d\.]+$', '', name_no_ext).strip().lower()
            filepath = os.path.join(root, filename)
            
            try:
                mtime_raw = os.path.getmtime(filepath)
            except Exception:
                continue 
            
            if base_name not in latest_files_group or mtime_raw > latest_files_group[base_name]['mtime_raw']:
                latest_files_group[base_name] = {'filename': filename, 'filepath': filepath, 'mtime_raw': mtime_raw}
                
        # 2. Second Pass: Process only the surviving "latest" versions
        for data in latest_files_group.values():
            filename = data['filename']
            source_path = data['filepath']
            ext = os.path.splitext(filename)[1].lower()
            
            # Deduplication Check (Exact Hash)
            file_hash = get_file_hash(source_path)
            if file_hash in seen_hashes or file_hash == "ERROR_UNREADABLE":
                continue
            seen_hashes.add(file_hash)
            
            # Routing Logic (Simplified!)
            if ext in ['.pdf', '.mp4', '.mov', '.avi']:
                route = "ROUTE_GEMINI_MULTIMODAL"
            else:
                route = "ROUTE_DEEPSEEK_TEXT"

            # Metadata Extraction
            try:
                size_bytes = os.path.getsize(source_path)
                c_time = datetime.fromtimestamp(os.path.getctime(source_path)).strftime('%Y-%m-%d %H:%M:%S')
                m_time = datetime.fromtimestamp(data['mtime_raw']).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                size_bytes = 0
                c_time = "UNKNOWN"
                m_time = "UNKNOWN"

            # Staging Copy
            rel_path = os.path.relpath(root, SOURCE_DIR)
            dest_folder = os.path.join(STAGING_DIR, rel_path)
            os.makedirs(dest_folder, exist_ok=True)
            
            staged_path = os.path.join(dest_folder, filename)
            try:
                shutil.copy2(source_path, staged_path)
                copied_count += 1
                print(f"Staged [{route}]: {filename}")
            except Exception as e:
                print(f"❌ Error copying {filename}: {e}")
                continue

            # Database Logging
            try:
                cursor.execute('''
                    INSERT INTO manifest (original_path, staged_path, filename, extension, hash, size_bytes, created_date, modified_date, route, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (source_path, staged_path, filename, ext, file_hash, size_bytes, c_time, m_time, route, 'PENDING_AI'))
                conn.commit()
            except sqlite3.IntegrityError:
                pass # Failsafe for unique hash constraint
                
            processed_count += 1

    conn.close()
    print("-" * 40)
    print(f"✅ ETL Complete! Processed {processed_count} unique, latest-version files.")
    print(f"📁 Copied {copied_count} files to {STAGING_DIR}")
    print(f"🗄️ Manifest database created at {DB_PATH}")

if __name__ == "__main__":
    build_manifest()