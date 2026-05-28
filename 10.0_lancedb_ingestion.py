import os
import sqlite3
import lancedb
import time
from google import genai
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
LANCEDB_PATH = os.path.join(STAGING_DIR, "career_brain_lancedb")
BATCH_SIZE = 100 
SAVE_EVERY = 1000 # Save to disk more frequently to protect progress!

# Initialize the new SDK Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
EMBEDDING_MODEL = "gemini-embedding-001"

def run_vectorization():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    # 1. Connect to SQLite and fetch all blocks
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, block_text FROM semantic_blocks")
    all_blocks = cursor.fetchall()
    conn.close()

    if not all_blocks:
        print("❌ No semantic blocks found in manifest.db!")
        return

    print(f"🚀 Loaded {len(all_blocks)} total Semantic Blocks.")

    # 2. Initialize LanceDB
    db = lancedb.connect(LANCEDB_PATH)
    table_name = "career_vectors"

    start_index = 0
    
    # Auto-Resume Logic: Try to open the table if it exists
    try:
        tbl = db.open_table(table_name)
        start_index = tbl.count_rows()
        print(f"🔄 Resuming from previously saved state: {start_index} vectors already in LanceDB.")
    except Exception:
        print(f"⚠️ Table '{table_name}' not found. Creating a fresh LanceDB table...")

    if start_index >= len(all_blocks):
        print("✅ All blocks have already been vectorized!")
        return

    # Slice the blocks to only process what is left
    blocks_to_process = all_blocks[start_index:]
    
    # 3. Batching & Embedding Loop
    data_to_insert = []
    total_processed = start_index

    print(f"🧠 Generating Embeddings via Gemini ({EMBEDDING_MODEL})...")

    for i in range(0, len(blocks_to_process), BATCH_SIZE):
        batch = blocks_to_process[i:i + BATCH_SIZE]
        ids = [b[0] for b in batch]
        texts = [b[1] for b in batch]

        # The Retry Shock Absorber
        success = False
        while not success:
            try:
                response = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts
                )

                for j, emb in enumerate(response.embeddings):
                    data_to_insert.append({
                        "block_id": ids[j],
                        "text": texts[j],
                        "vector": emb.values
                    })
                
                success = True # Break out of the retry loop
                total_processed += len(batch)

            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    print(f"⏳ Speed limit hit at batch {total_processed}! Google needs a breather. Waiting 10 seconds...")
                    time.sleep(10)
                else:
                    print(f"❌ Error on batch {total_processed}: {e}. Retrying in 5 seconds...")
                    time.sleep(5)

        # Save to LanceDB
        if len(data_to_insert) >= SAVE_EVERY or i + BATCH_SIZE >= len(blocks_to_process):
            # Using exist_ok=True ensures it creates the table on the first run, 
            # and we simply use tbl.add() if it already exists.
            if start_index == 0 and total_processed <= SAVE_EVERY:
                tbl = db.create_table(table_name, data=data_to_insert, exist_ok=True)
            else:
                tbl = db.open_table(table_name)
                tbl.add(data_to_insert)
            
            print(f"💾 Saved {total_processed}/{len(all_blocks)} vectors to LanceDB...")
            data_to_insert = [] # Clear the payload memory
            
        # The Cruise Control: Stay under 3,000 items per minute
        time.sleep(2.5) 

    print("\n🏁 --- VECTORIZATION COMPLETE --- 🏁")
    print(f"Your Career Brain is officially alive at: {LANCEDB_PATH}")

if __name__ == "__main__":
    run_vectorization()