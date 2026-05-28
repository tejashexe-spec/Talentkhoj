import pymysql
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
                    avatar VARCHAR(255) DEFAULT NULL,
                    bio TEXT DEFAULT NULL,
                    location VARCHAR(255) DEFAULT NULL,
                    skills TEXT DEFAULT NULL,
                    cv_path VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

    def _run_migrations(self):
        """Add any missing columns to existing tables."""
        migrations = [
            ("avatar",   "ALTER TABLE users ADD COLUMN avatar VARCHAR(255) DEFAULT NULL"),
            ("bio",      "ALTER TABLE users ADD COLUMN bio TEXT DEFAULT NULL"),
            ("location", "ALTER TABLE users ADD COLUMN location VARCHAR(255) DEFAULT NULL"),
            ("skills",   "ALTER TABLE users ADD COLUMN skills TEXT DEFAULT NULL"),
            ("cv_path",  "ALTER TABLE users ADD COLUMN cv_path VARCHAR(255) DEFAULT NULL"),
        ]
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'",
                (config.MYSQL_DATABASE,)
            )
            existing = {row["COLUMN_NAME"] for row in cursor.fetchall()}

        for col, sql in migrations:
            if col not in existing:
                with self.__connection.cursor() as cursor:
                    cursor.execute(sql)

    def get_connection(self):
        return self.__connection
