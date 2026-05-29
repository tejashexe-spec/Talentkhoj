import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_first_flask.model.database import Database

db = Database()
conn = db.get_connection()

with conn.cursor() as cursor:
    cursor.execute("SELECT * FROM mail_logs ORDER BY created_at DESC LIMIT 5")
    logs = cursor.fetchall()
    
    print("\n=== Latest 5 Mail Logs ===\n")
    for i, log in enumerate(logs, 1):
        print(f"--- Log {i} ---")
        print(f"  ID: {log['id']}")
        print(f"  To: {log['to_email']}")
        print(f"  Subject: {log['subject']}")
        print(f"  Status: {log['status']}")
        if log['error_message']:
            print(f"  Error: {log['error_message']}")
        print(f"  Sent at: {log['created_at']}")
        print()
