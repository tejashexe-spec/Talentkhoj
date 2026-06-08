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
            self._seed_mock_reviews()
            print("Database connected successfully!")

        except pymysql.MySQLError as e:
            print("Database connection failed!")
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
                    cv_data TEXT DEFAULT NULL,
                    email_verified TINYINT(1) NOT NULL DEFAULT 0,
                    verification_token VARCHAR(255) DEFAULT NULL,
                    verification_token_expires_at TIMESTAMP NULL DEFAULT NULL,
                    reset_password_token VARCHAR(255) DEFAULT NULL,
                    reset_password_token_expires_at TIMESTAMP NULL DEFAULT NULL,
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
                CREATE TABLE IF NOT EXISTS mail_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    from_email VARCHAR(255) NOT NULL,
                    to_email VARCHAR(255) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    html_content TEXT,
                    status ENUM('success', 'failed') NOT NULL,
                    error_message TEXT,
                    resend_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    opportunity_type ENUM('job', 'internship', 'event') NOT NULL DEFAULT 'job',
                    location VARCHAR(255) DEFAULT NULL,
                    salary VARCHAR(255) DEFAULT NULL,
                    experience_level VARCHAR(255) DEFAULT NULL,
                    skills_required TEXT DEFAULT NULL,
                    description TEXT NOT NULL,
                    apply_link VARCHAR(255) DEFAULT NULL,
                    questions TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    job_id INT NOT NULL,
                    status ENUM('applied', 'reviewed', 'shortlisted', 'rejected') NOT NULL DEFAULT 'applied',
                    answers TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_user_job (user_id, job_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    job_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_user_bookmark (user_id, job_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    reviewer_id INT NOT NULL,
                    reviewee_id INT NOT NULL,
                    rating INT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (reviewee_id) REFERENCES users(id) ON DELETE CASCADE
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    content TEXT NOT NULL,
                    image_path VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_user_post (user_id),
                    INDEX idx_post_created (created_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reactions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    post_id INT NOT NULL,
                    reaction_type VARCHAR(50) DEFAULT 'like',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_user_post_reaction (user_id, post_id, reaction_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    post_id INT NOT NULL,
                    parent_comment_id INT DEFAULT NULL,
                    comment_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_comment_id) REFERENCES comments(id) ON DELETE CASCADE,
                    INDEX idx_post_comments (post_id, parent_comment_id)
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
            ("cv_data",      "ALTER TABLE users ADD COLUMN cv_data TEXT DEFAULT NULL"),
            ("account_type", "ALTER TABLE users ADD COLUMN account_type ENUM('individual','company') NOT NULL DEFAULT 'individual'"),
            ("email_verified", "ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 0"),
            ("verification_token", "ALTER TABLE users ADD COLUMN verification_token VARCHAR(255) DEFAULT NULL"),
            ("verification_token_expires_at", "ALTER TABLE users ADD COLUMN verification_token_expires_at TIMESTAMP NULL DEFAULT NULL"),
            ("reset_password_token", "ALTER TABLE users ADD COLUMN reset_password_token VARCHAR(255) DEFAULT NULL"),
            ("reset_password_token_expires_at", "ALTER TABLE users ADD COLUMN reset_password_token_expires_at TIMESTAMP NULL DEFAULT NULL"),
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

        # Jobs table migrations (questions column)
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'jobs'",
                (config.MYSQL_DATABASE,)
            )
            existing_jobs = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            
        if "questions" not in existing_jobs:
            with self.__connection.cursor() as cursor:
                cursor.execute("ALTER TABLE jobs ADD COLUMN questions TEXT DEFAULT NULL")

        # Applications table migrations (answers column & status index)
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'applications'",
                (config.MYSQL_DATABASE,)
            )
            existing_apps = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            
        if "answers" not in existing_apps:
            with self.__connection.cursor() as cursor:
                cursor.execute("ALTER TABLE applications ADD COLUMN answers TEXT DEFAULT NULL")

        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT INDEX_NAME FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'applications' AND INDEX_NAME = 'idx_status'",
                (config.MYSQL_DATABASE,)
            )
            existing_index = cursor.fetchone()

        if not existing_index:
            with self.__connection.cursor() as cursor:
                cursor.execute("ALTER TABLE applications ADD INDEX idx_status (status)")


    def get_connection(self):
        return self.__connection

    def _seed_mock_reviews(self):
        """Seed mock reviews if the reviews table is empty."""
        with self.__connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM reviews")
            if cursor.fetchone()["cnt"] == 0:
                cursor.execute("SELECT id FROM users WHERE account_type = 'individual' LIMIT 1")
                candidate = cursor.fetchone()
                cursor.execute("SELECT id FROM users WHERE account_type = 'company' LIMIT 1")
                company = cursor.fetchone()
                
                if candidate and company:
                    candidate_id = candidate["id"]
                    company_id = company["id"]
                    
                    cursor.execute("""
                        INSERT INTO reviews (reviewer_id, reviewee_id, rating, comment)
                        VALUES 
                        (%s, %s, 5, 'Exceptional experience interviewing with this company. Very transparent and modern tech stack.'),
                        (%s, %s, 4, 'Outstanding candidate with deep problem-solving skills and a solid understanding of web development frameworks.')
                    """, (candidate_id, company_id, company_id, candidate_id))
