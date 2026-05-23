import pymysql
from my_first_flask import config


class Database:
    _instance = None

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
            print("Database connected successfully!")

        except pymysql.MySQLError as e:
            print("Database connection failed!")
            print("Error:", e)
            self.__connection = None

    def _init_tables(self):
        if not self.__connection:
            return

        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    full_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    avatar VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

    def fetch_one(self, query, params=()):
        if not self.__connection:
            return None
        with self.__connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute(self, query, params=()):
        if not self.__connection:
            return False
        with self.__connection.cursor() as cursor:
            cursor.execute(query, params)
            self.__connection.commit()
            return True
    def get_connection(self):
        return self.__connection
