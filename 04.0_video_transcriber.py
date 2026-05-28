import os
import sqlite3
from faster_whisper import WhisperModel
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR")
DB_PATH = os.path.join(STAGING_DIR, "manifest.db")

# Model size: 'base' or 'small' is extremely fast and good enough for AI triage. 
# 'base' requires ~1GB of RAM.
WHISPER_MODEL_SIZE = "base" 

def setup_database_updates(cursor):
    """Patches the database to store the transcript path."""
    try:
        cursor.execute("ALTER TABLE manifest ADD COLUMN transcript_path TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists

def run_transcriber():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    setup_database_updates(cursor)

    # Find all unprocessed video files
    cursor.execute('''
        SELECT id, filename, staged_path 
        FROM manifest 
        WHERE status = 'PENDING_AI' 
        AND extension IN ('.mp4', '.mov', '.avi')
        AND (transcript_path IS NULL OR transcript_path = '')
    ''')
    videos = cursor.fetchall()

    if not videos:
        print("No pending videos found to transcribe.")
        conn.close()
        return

    print(f"Found {len(videos)} videos. Loading local Whisper model '{WHISPER_MODEL_SIZE}'...")
    print("This runs entirely on your local machine. No API costs.\n")
    
    # Load model (Runs on CPU by default to ensure maximum compatibility)
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

    processed_count = 0

    for file_id, filename, staged_path in videos:
        if not os.path.exists(staged_path):
            continue

        transcript_path = staged_path + ".txt"
        print(f"🎙️ Transcribing: {filename}...")

        try:
            # Transcribe the audio
            segments, info = model.transcribe(staged_path, beam_size=5)
            
            # Combine the segments into one text block
            full_text = []
            for segment in segments:
                full_text.append(segment.text)
            
            transcript_text = " ".join(full_text).strip()
            
            if not transcript_text:
                transcript_text = "[SILENCE / NO SPOKEN AUDIO DETECTED]"

            # Save to a local text file
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)

            # Update the database to route it to DeepSeek!
            cursor.execute('''
                UPDATE manifest 
                SET transcript_path = ?, route = 'ROUTE_DEEPSEEK_TEXT'
                WHERE id = ?
            ''', (transcript_path, file_id))
            conn.commit()
            
            processed_count += 1
            print(f"✅ Saved transcript for {filename}")

        except Exception as e:
            print(f"❌ Error transcribing {filename}: {e}")

    conn.close()
    print("-" * 40)
    print(f"🎯 Transcription Complete! Converted {processed_count} videos to text for AI Triage.")

if __name__ == "__main__":
    run_transcriber()