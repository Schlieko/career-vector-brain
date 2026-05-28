import os
import sqlite3
from dotenv import load_dotenv

# Load paths
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")

def generate_report():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n📊 --- AI TRIAGE EXECUTIVE SUMMARY --- 📊\n")

    # 1. The High-Level Tally (Grouping by Status)
    cursor.execute('''
        SELECT status, COUNT(*) 
        FROM manifest 
        GROUP BY status 
        ORDER BY COUNT(*) DESC
    ''')
    statuses = cursor.fetchall()
    
    print("STATUS BREAKDOWN:")
    for status, count in statuses:
        print(f"  • {status}: {count:,} files")

    print("\n" + "-"*40 + "\n")

    # 2. The DeepSeek Classifications (For files it actually read)
    # FIX: FROM clause moved above the WHERE clause!
    cursor.execute('''
        SELECT ai_classification, COUNT(*) 
        FROM manifest
        WHERE ai_classification IS NOT NULL AND ai_classification != ''
        GROUP BY ai_classification 
        ORDER BY COUNT(*) DESC
    ''')
    classifications = cursor.fetchall()
    
    if classifications:
        print("AI CLASSIFICATIONS (What DeepSeek saw):")
        for classification, count in classifications:
            print(f"  • [{classification}]: {count:,} files")
            
    print("\n" + "-"*40 + "\n")
    
    # 3. Calculate Final Survival Rate
    cursor.execute("SELECT COUNT(*) FROM manifest WHERE status = 'APPROVED_FOR_EXTRACTION'")
    approved_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM manifest")
    total_count = cursor.fetchone()[0]
    
    if total_count > 0:
        survival_rate = (approved_count / total_count) * 100
        print(f"🏆 TOTAL APPROVED FOR VECTORIZATION: {approved_count:,} ({survival_rate:.1f}% of total archive)")

    conn.close()
    print("\n=========================================\n")

if __name__ == "__main__":
    generate_report()