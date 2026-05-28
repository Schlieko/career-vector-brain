import sqlite3
import re
import os
from collections import Counter
from dotenv import load_dotenv

# Load your .env file paths
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")

def check_fuzzy_patterns():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Grab every file that was successfully staged
    cursor.execute("SELECT filename FROM manifest WHERE status = 'PENDING_AI'")
    files = cursor.fetchall()

    pattern_counts = Counter()

    for file_tuple in files:
        filename = file_tuple[0]
        
        # 1. Remove the file extension
        name_no_ext = os.path.splitext(filename)[0].lower()
        
        # 2. Strip out all numbers (so "Report 2024" and "Report 2025" become just "report")
        no_numbers = re.sub(r'\d+', '', name_no_ext)
        
        # 3. Replace all punctuation/symbols with a single space and strip edges
        base_pattern = re.sub(r'[^a-z]+', ' ', no_numbers).strip()
        
        if not base_pattern:
            base_pattern = "[NUMBERS/SYMBOLS ONLY]"

        pattern_counts[base_pattern] += 1

    print(f"Total files analyzed: {len(files)}")
    print("\n--- TOP 50 REPEATING FILE PATTERNS ---")
    print("(If a pattern has 50+ files, it might be system-generated noise!)\n")
    
    # Print the top 50 patterns, but only if they appear more than once
    for pattern, count in pattern_counts.most_common(50):
        if count > 1:
            print(f"[{count} files] -> Pattern: '{pattern}'")

    conn.close()

if __name__ == "__main__":
    check_fuzzy_patterns()