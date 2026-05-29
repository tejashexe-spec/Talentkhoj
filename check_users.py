import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_first_flask.model.database import Database

db = Database()
conn = db.get_connection()

with conn.cursor() as cursor:
    cursor.execute("SELECT id, full_name, email, email_verified FROM users")
    users = cursor.fetchall()
    
    print(f"\n=== Users in Database ===\n")
    for user in users:
        print(f"ID: {user['id']}")
        print(f"Name: {user['full_name']}")
        print(f"Email: {user['email']}")
        print(f"Verified: {'Yes' if user['email_verified'] else 'No'}")
        print()
