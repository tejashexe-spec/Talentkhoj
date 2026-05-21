import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "secret_key")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "talent_khoj")
