import os
import pandas as pd
from collections import Counter
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
DROP_DIR = os.path.join(STAGING_DIR, "custom_drops")
REPORT_PATH = "email_recipients_report.txt"

def run_email_recon():
    if not os.path.exists(DROP_DIR):
        print(f"❌ Error: {DROP_DIR} not found.")
        return

    # Find the CSV file
    csv_files = [f for f in os.listdir(DROP_DIR) if f.endswith('.csv')]
    if not csv_files:
        print(f"⚠️ No CSV files found in {DROP_DIR}.")
        return

    csv_path = os.path.join(DROP_DIR, csv_files[0])
    print(f"🚀 Found email dataset: {csv_files[0]}. Scanning recipients...")

    try:
        # TRY UTF-8 FIRST, FALLBACK TO WINDOWS ENCODING
        try:
            df = pd.read_csv(csv_path, encoding='utf-8', on_bad_lines='skip', low_memory=False)
        except UnicodeDecodeError:
            print("⚠️ UTF-8 encoding failed (Classic Excel quirk). Falling back to Windows encoding...")
            df = pd.read_csv(csv_path, encoding='cp1252', on_bad_lines='skip', low_memory=False)
        
        # Look for standard 'To' column names
        to_column = None
        for col in ['DisplayTo', 'To', 'Recipient', 'ToAddress']:
            if col in df.columns:
                to_column = col
                break
                
        if not to_column:
            print(f"❌ Could not find a 'To' or 'DisplayTo' column. Found columns: {list(df.columns)}")
            return
            
        print(f"✅ Found recipient column: '{to_column}'")

        # Tally the recipients
        recipient_counts = Counter()
        
        # Drop empty rows and count
        recipients = df[to_column].dropna().astype(str)
        for person in recipients:
            clean_person = person.strip().lower()
            recipient_counts[clean_person] += 1

        # Write to report
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write("=========================================\n")
            f.write("      EMAIL RECIPIENT RECON REPORT\n")
            f.write("=========================================\n")
            f.write(f"Total Emails Scanned: {len(df)}\n")
            f.write(f"Total Unique Recipients: {len(recipient_counts)}\n")
            f.write("=========================================\n\n")
            
            f.write("--- TOP 100 RECIPIENTS ---\n")
            f.write("(Add personal/admin contacts from here to 'email_assassin_targets.txt')\n\n")
            
            for person, count in recipient_counts.most_common(100):
                f.write(f"[{count} emails] -> {person}\n")

        print(f"🎯 Recon complete! Report saved to {REPORT_PATH}")
        print("➡️ Review the list and copy personal contacts to your assassin targets file.")

    except Exception as e:
        print(f"❌ Error reading CSV: {e}")

if __name__ == "__main__":
    run_email_recon()