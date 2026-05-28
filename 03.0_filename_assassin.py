import os
import sqlite3
from dotenv import load_dotenv

# Load paths from your .env file
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
TARGETS_FILE = "assassin_targets.txt"

def load_assassin_targets():
    """Reads the non-hardcoded targets file and extracts valid patterns."""
    if not os.path.exists(TARGETS_FILE):
        print(f"❌ Error: {TARGETS_FILE} not found. Please create it first.")
        return []
        
    patterns = []
    with open(TARGETS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            clean_line = line.strip().lower()
            if clean_line and not clean_line.startswith('#'):
                patterns.append(clean_line)
    return patterns

def execute_assassination():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    targets = load_assassin_targets()
    if not targets:
        print("No targets found to eliminate. Exiting.")
        return

    print(f"Loaded {len(targets)} junk patterns from {TARGETS_FILE}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Grab all files currently marked as pending, including their full staged paths
    cursor.execute("SELECT id, filename, staged_path FROM manifest WHERE status = 'PENDING_AI'")
    staged_files = cursor.fetchall()
    
    deleted_count = 0
    
    print("Scanning staging area for matching targets...\n")
    
    for file_id, filename, staged_path in staged_files:
        filename_lower = filename.lower()
        staged_path_lower = staged_path.lower()
        name_no_ext = os.path.splitext(filename_lower)[0].strip()
        match_found = False
        
        # --- VIP OVERRIDE ---
        # If it's your personal activity or email data, it gets total immunity!
        if 'activity' in filename_lower or 'takeout' in filename_lower or filename_lower == 'email.csv':
            continue

        for target in targets:
            # 1. FOLDER ASSASSIN LOGIC (If the target contains a slash)
            if '\\' in target or '/' in target:
                # Normalize slashes so \adobe\ matches regardless of OS
                normalized_target = target.replace('\\', os.sep).replace('/', os.sep)
                if normalized_target in staged_path_lower:
                    match_found = True
                    break

            # 2. Special logic for numbers/symbols flag
            elif target == "[numbers/symbols only]" and not any(c.isalpha() for c in name_no_ext):
                match_found = True
                break
                
            # 3. SAFEGUARD: If target is short (2 chars or less), require EXACT match on base filename
            elif len(target) <= 2:
                if name_no_ext == target:
                    match_found = True
                    break
                    
            # 4. Standard substring match for longer phrases (e.g., 'distribution email')
            else:
                if target in filename_lower:
                    match_found = True
                    break
                
        if match_found:
            cursor.execute('''
                UPDATE manifest 
                SET route = 'TRASH_FILENAME_ASSASSIN', status = 'TRASHED' 
                WHERE id = ?
            ''', (file_id,))
            
            if os.path.exists(staged_path):
                try:
                    os.remove(staged_path)
                    print(f"🔥 Deleted: {filename}")
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ Could not physically remove {filename}: {e}")
                    
    conn.commit()
    conn.close()
    
    print("-" * 40)
    print(f"💥 Operation Complete! Safely eliminated {deleted_count} junk files from Staging.")
    print("🗄️ Manifest database updated cleanly.")

if __name__ == "__main__":
    execute_assassination()