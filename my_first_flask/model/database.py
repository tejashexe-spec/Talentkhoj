import pymysql
from datetime import datetime, timedelta
from my_first_flask import config


class Database:
    def __init__(self):
        try:
            # Create database if it doesn't exist
            bootstrap = pymysql.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                cursorclass=pymysql.cursors.DictCursor,
            )
            with bootstrap.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{config.MYSQL_DATABASE}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            bootstrap.close()

            self.__connection = pymysql.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            self._init_tables()
            self._run_migrations()
            self._seed_mock_events()
            print("✅ Database connected successfully!")

        except pymysql.MySQLError as e:
            print("❌ Database connection failed!")
            print("Error:", e)
            self.__connection = None

    def _init_tables(self):
        """Create tables if they don't exist."""
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    full_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    account_type ENUM('individual', 'company') NOT NULL DEFAULT 'individual',
                    avatar VARCHAR(255) DEFAULT NULL,
                    bio TEXT DEFAULT NULL,
                    location VARCHAR(255) DEFAULT NULL,
                    skills TEXT DEFAULT NULL,
                    cv_path VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    company_name VARCHAR(255) NOT NULL,
                    address VARCHAR(255) DEFAULT NULL,
                    pan_number VARCHAR(50) DEFAULT NULL,
                    industry VARCHAR(255) DEFAULT NULL,
                    website VARCHAR(255) DEFAULT NULL,
                    description TEXT DEFAULT NULL,
                    logo VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    event_date DATETIME NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    registration_link VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

    def _run_migrations(self):
        """Add any missing columns to existing tables."""
        # Users table migrations
        user_migrations = [
            ("avatar",       "ALTER TABLE users ADD COLUMN avatar VARCHAR(255) DEFAULT NULL"),
            ("bio",          "ALTER TABLE users ADD COLUMN bio TEXT DEFAULT NULL"),
            ("location",     "ALTER TABLE users ADD COLUMN location VARCHAR(255) DEFAULT NULL"),
            ("skills",       "ALTER TABLE users ADD COLUMN skills TEXT DEFAULT NULL"),
            ("cv_path",      "ALTER TABLE users ADD COLUMN cv_path VARCHAR(255) DEFAULT NULL"),
            ("account_type", "ALTER TABLE users ADD COLUMN account_type ENUM('individual','company') NOT NULL DEFAULT 'individual'"),
        ]
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'",
                (config.MYSQL_DATABASE,)
            )
            existing_users = {row["COLUMN_NAME"] for row in cursor.fetchall()}

        for col, sql in user_migrations:
            if col not in existing_users:
                with self.__connection.cursor() as cursor:
                    cursor.execute(sql)

        # Companies table migrations
        companies_migrations = [
            ("address",    "ALTER TABLE companies ADD COLUMN address VARCHAR(255) DEFAULT NULL"),
            ("pan_number", "ALTER TABLE companies ADD COLUMN pan_number VARCHAR(50) DEFAULT NULL"),
        ]
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'companies'",
                (config.MYSQL_DATABASE,)
            )
            existing_companies = {row["COLUMN_NAME"] for row in cursor.fetchall()}

        for col, sql in companies_migrations:
            if col not in existing_companies:
                with self.__connection.cursor() as cursor:
                    cursor.execute(sql)

    def get_connection(self):
        return self.__connection

    def _seed_mock_events(self):
        """Seed mock events if the events table is empty."""
        with self.__connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM events")
            if cursor.fetchone()["cnt"] == 0:
                # Find a company to attach the events to
                cursor.execute("SELECT id FROM companies LIMIT 1")
                company = cursor.fetchone()
                if company:
                    company_id = company["id"]
                    cursor.execute("""
                        INSERT INTO events (company_id, title, description, event_date, location, registration_link)
                        VALUES 
                        (%s, 'Resume Building & Interview Prep Masterclass', 'Join our engineering and talent acquisition teams to learn how to stand out in technical interviews and craft a world-class software engineering CV.', %s, 'Virtual - Google Meet', 'https://meet.google.com'),
                        (%s, 'Talent Khoj Virtual Networking & Career Fair 2026', 'Connect directly with hiring managers, ask questions about open roles, and get fast-tracked for upcoming software engineer, designer, and PM roles.', %s, 'Pragati Manzil Event Hall / Hybrid', 'https://talentkhoj.com/register')
                    """, (
                        company_id, datetime.now() + timedelta(days=5),
                        company_id, datetime.now() + timedelta(days=10)
                    ))
                    print("✅ Mock events seeded successfully!")
