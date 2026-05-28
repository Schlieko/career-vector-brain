import os
import sqlite3
from dotenv import load_dotenv

# Connect to the database
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Count every single block in the table
cursor.execute("SELECT count(*) FROM semantic_blocks")
total_blocks = cursor.fetchone()[0]

print("\n" + "="*50)
print(f" 🧠 TOTAL SEMANTIC BLOCKS GENERATED: {total_blocks:,}")
print("="*50 + "\n")

conn.close()