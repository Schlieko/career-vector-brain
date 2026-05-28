import sqlite3

# Connect to your tracking database
conn = sqlite3.connect('C:/vector_staging/manifest.db')

# Reset the JSON files so Script 08 will read them again
conn.execute("UPDATE manifest SET status = 'APPROVED_FOR_EXTRACTION' WHERE filename LIKE '%.json'")

conn.commit()
conn.close()

print("✅ JSON reset successful! You are ready for Script 08.")