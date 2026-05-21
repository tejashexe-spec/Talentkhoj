import pymysql
from my_first_flask import config


class Database:
    def __init__(self):
        try:
            self.__connection = pymysql.connect(
                host=config.MYSQL_HOST,
                user=config.MYSQL_USER,
                password=config.MYSQL_PASSWORD,
                database=config.MYSQL_DATABASE,
                cursorclass=pymysql.cursors.DictCursor,
            )
            print("Database connected successfully!")

        except pymysql.MySQLError as e:
            print("Database connection failed!")
            print("Error:", e)

    def fetch_one(self, query, params=()):
        if not self.__connection: return None
        with self.__connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute(self, query, params=()):
        if not self.__connection: return False
        with self.__connection.cursor() as cursor:
            cursor.execute(query, params)
            self.__connection.commit()
            return True
