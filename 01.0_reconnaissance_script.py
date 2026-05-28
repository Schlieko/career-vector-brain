import os
from collections import Counter
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SOURCE_DIR = os.getenv("SOURCE_DIR")
REPORT_PATH = "extensions_report.txt"

def run_reconnaissance():
    if not SOURCE_DIR or not os.path.exists(SOURCE_DIR):
        print("❌ Error: SOURCE_DIR is invalid or not set in your .env file.")
        return

    print(f"Starting pure reconnaissance scan of {SOURCE_DIR}...")
    print("Counting all file extensions. This might take a minute...\n")

    extension_counts = Counter()
    total_files = 0

    # Walk the directory and count extensions
    for root, _, files in os.walk(SOURCE_DIR):
        for file in files:
            total_files += 1
            ext = os.path.splitext(file)[1].lower()
            
            # Handle files with no extension
            if not ext:
                ext = "No Extension"
                
            extension_counts[ext] += 1

    # Write the results to a clean text report
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write("=========================================\n")
        f.write("      RECONNAISSANCE REPORT\n")
        f.write("=========================================\n")
        f.write(f"Target Directory: {SOURCE_DIR}\n")
        f.write(f"Total Files Scanned: {total_files}\n")
        f.write(f"Total Unique Extensions: {len(extension_counts)}\n")
        f.write("=========================================\n\n")
        
        f.write("--- TOP 100 EXTENSIONS ---\n")
        for ext, count in extension_counts.most_common(100):
            f.write(f"{ext}: {count} files\n")

    print(f"✅ Scan complete! Analyzed {total_files} files.")
    print(f"📄 Report generated: {REPORT_PATH}")
    print("➡️ Open the report to see what lives on your drive, then add your chosen extensions to 'target_extensions.txt'.")

if __name__ == "__main__":
    run_reconnaissance()