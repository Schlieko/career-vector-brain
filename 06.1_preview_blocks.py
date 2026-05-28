import os
import sqlite3
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")

def preview_blocks():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Grab 5 random blocks to spot-check the Flash model's quality
        cursor.execute('''
            SELECT m.filename, s.block_text 
            FROM semantic_blocks s
            JOIN manifest m ON s.manifest_id = m.id
            ORDER BY RANDOM()
            LIMIT 5
        ''')
        blocks = cursor.fetchall()
        
        if not blocks:
            print("⚠️ No blocks found! The extraction script might not have finished a file yet.")
            return
            
        print(f"\n🔍 --- PREVIEWING {len(blocks)} SEMANTIC BLOCKS --- 🔍\n")
        
        for i, (filename, block_text) in enumerate(blocks, 1):
            print(f"BLOCK {i} (Parent File: {filename})")
            print("-" * 50)
            print(block_text)
            print("\n" + "=" * 50 + "\n")
            
        # Get the total count of blocks generated so far
        cursor.execute("SELECT COUNT(*) FROM semantic_blocks")
        total_blocks = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT manifest_id) FROM semantic_blocks")
        total_files = cursor.fetchone()[0]
        
        print(f"📊 SUMMARY: Generated {total_blocks} total blocks from {total_files} files so far.")
        
    except sqlite3.OperationalError:
        print("❌ Error: The 'semantic_blocks' table doesn't exist yet! Run Script 06 first.")

    conn.close()

if __name__ == "__main__":
    preview_blocks()