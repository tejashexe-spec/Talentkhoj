import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from my_first_flask import config
import pymysql

conn = pymysql.connect(
    host=config.MYSQL_HOST,
    user=config.MYSQL_USER,
    password=config.MYSQL_PASSWORD,
    database=config.MYSQL_DATABASE,
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with conn.cursor() as cursor:
        print("Current columns in users table:")
        cursor.execute("DESCRIBE users")
        columns = cursor.fetchall()
        for col in columns:
            print(f"- {col['Field']} ({col['Type']})")
        
        print("\nChecking and adding missing columns...")
        
        # Add email_verified
        cursor.execute("SHOW COLUMNS FROM users LIKE 'email_verified'")
        if not cursor.fetchone():
            print("Adding email_verified column...")
            cursor.execute("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE")
        
        # Add verification_token
        cursor.execute("SHOW COLUMNS FROM users LIKE 'verification_token'")
        if not cursor.fetchone():
            print("Adding verification_token column...")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_token VARCHAR(255) DEFAULT NULL")
        
        # Add verification_token_expires_at
        cursor.execute("SHOW COLUMNS FROM users LIKE 'verification_token_expires_at'")
        if not cursor.fetchone():
            print("Adding verification_token_expires_at column...")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_token_expires_at DATETIME DEFAULT NULL")
        
        # Add reset_password_token
        cursor.execute("SHOW COLUMNS FROM users LIKE 'reset_password_token'")
        if not cursor.fetchone():
            print("Adding reset_password_token column...")
            cursor.execute("ALTER TABLE users ADD COLUMN reset_password_token VARCHAR(255) DEFAULT NULL")
        
        # Add reset_password_token_expires_at
        cursor.execute("SHOW COLUMNS FROM users LIKE 'reset_password_token_expires_at'")
        if not cursor.fetchone():
            print("Adding reset_password_token_expires_at column...")
            cursor.execute("ALTER TABLE users ADD COLUMN reset_password_token_expires_at DATETIME DEFAULT NULL")
        
        print("\nAll columns are now up to date!")
    conn.commit()
finally:
    conn.close()
