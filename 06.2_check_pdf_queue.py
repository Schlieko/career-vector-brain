import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.path.join(os.getenv("STAGING_DIR"), "manifest.db")

def check_queue():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Count pending PDFs
    cursor.execute('''
        SELECT COUNT(*) 
        FROM manifest 
        WHERE status = 'APPROVED_FOR_EXTRACTION' 
        AND route = 'ROUTE_GEMINI_MULTIMODAL'
        AND extension = '.pdf'
    ''')
    pdf_count = cursor.fetchone()[0]

    # Get a rough size estimate (in MB) to gauge complexity
    cursor.execute('''
        SELECT SUM(size_bytes) 
        FROM manifest 
        WHERE status = 'APPROVED_FOR_EXTRACTION' 
        AND route = 'ROUTE_GEMINI_MULTIMODAL'
        AND extension = '.pdf'
    ''')
    total_bytes = cursor.fetchone()[0] or 0
    total_mb = total_bytes / (1024 * 1024)

    print("\n📊 --- GEMINI PDF QUEUE STATUS --- 📊")
    print(f"Total PDFs waiting for Gemini: {pdf_count:,}")
    print(f"Total File Size: {total_mb:.2f} MB")
    print("-" * 35 + "\n")

    conn.close()

if __name__ == "__main__":
    check_queue()