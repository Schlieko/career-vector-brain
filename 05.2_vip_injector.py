import os
import sqlite3
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")
VIP_DIR = os.path.join(STAGING_DIR, "custom_drops")

# --- 2. MAIN INJECTION LOGIC ---
def inject_vips():
    if not os.path.exists(VIP_DIR):
        print(f"❌ VIP folder not found at {VIP_DIR}")
        print("Please ensure the folder exists and your files are inside.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    vip_files = [f for f in os.listdir(VIP_DIR) if os.path.isfile(os.path.join(VIP_DIR, f))]
    
    if not vip_files:
        print(f"⚠️ No files found in {VIP_DIR}")
        conn.close()
        return

    print(f"🌟 Found {len(vip_files)} VIP files. Injecting into database...\n")

    for filename in vip_files:
        filepath = os.path.join(VIP_DIR, filename)
        size_bytes = os.path.getsize(filepath)
        
        # Extract extension and convert to lowercase
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # Check for duplicates using filename instead of a hash column
        cursor.execute("SELECT id FROM manifest WHERE filename = ?", (filename,))
        existing_record = cursor.fetchone()

        if existing_record:
            # Force update it to the VIP status just to be absolutely sure
            cursor.execute('''
                UPDATE manifest 
                SET status = 'APPROVED_FOR_EXTRACTION', 
                    route = 'ROUTE_DEEPSEEK_TEXT',
                    ai_classification = 'VIP_CORE_IP',
                    ai_reason = 'Manual VIP Injection'
                WHERE filename = ?
            ''', (filename,))
            print(f"🔄 Updated existing record to VIP: {filename}")
        else:
            # Insert brand new record using only confirmed columns
            cursor.execute('''
                INSERT INTO manifest (
                    filename, original_path, staged_path, 
                    extension, size_bytes, status, route, 
                    ai_classification, ai_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filename, filepath, filepath, 
                ext, size_bytes, 'APPROVED_FOR_EXTRACTION', 'ROUTE_DEEPSEEK_TEXT',
                'VIP_CORE_IP', 'Manual VIP Injection'
            ))
            print(f"✅ Injected brand new VIP: {filename}")

    conn.commit()
    conn.close()
    
    print("\n🎯 VIP Injection Complete! Your custom files are now in the final extraction queue.")

if __name__ == "__main__":
    inject_vips()