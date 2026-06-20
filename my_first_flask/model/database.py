import pymysql
import threading
from datetime import datetime, timedelta
from my_first_flask import config


class Database:
    def __init__(self):
        self._local = threading.local()
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
            self._seed_mock_saved_searches()
            self._seed_community_data()
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
                    account_type ENUM('individual', 'company', 'admin') NOT NULL DEFAULT 'individual',
                    avatar VARCHAR(255) DEFAULT NULL,
                    bio TEXT DEFAULT NULL,
                    location VARCHAR(255) DEFAULT NULL,
                    skills TEXT DEFAULT NULL,
                    cv_path VARCHAR(255) DEFAULT NULL,
                    cv_data TEXT DEFAULT NULL,
                    resume_analysis LONGTEXT DEFAULT NULL,
                    email_verified TINYINT(1) NOT NULL DEFAULT 0,
                    verification_token VARCHAR(255) DEFAULT NULL,
                    verification_token_expires_at TIMESTAMP NULL DEFAULT NULL,
                    reset_password_token VARCHAR(255) DEFAULT NULL,
                    reset_password_token_expires_at TIMESTAMP NULL DEFAULT NULL,
                    active_status ENUM('actively_looking', 'open_to_offers', 'not_looking') NOT NULL DEFAULT 'actively_looking',
                    headhunting_mode TINYINT(1) NOT NULL DEFAULT 1,
                    verified TINYINT(1) NOT NULL DEFAULT 0,
                    is_banned TINYINT(1) NOT NULL DEFAULT 0,
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
                    sector VARCHAR(255) DEFAULT NULL,
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
                CREATE TABLE IF NOT EXISTS messages (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sender_id INT NOT NULL,
                    receiver_id INT NOT NULL,
                    message_text TEXT NOT NULL,
                    is_read TINYINT(1) NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE,
                    INDEX idx_sender_receiver (sender_id, receiver_id),
                    INDEX idx_receiver_sender (receiver_id, sender_id)
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
                CREATE TABLE IF NOT EXISTS event_rsvps (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    event_id INT NOT NULL,
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_event_user (event_id, user_id)
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_badges (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    company_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    badge_type ENUM('internship', 'employment', 'contribution', 'other') NOT NULL DEFAULT 'employment',
                    description TEXT DEFAULT NULL,
                    start_date DATE DEFAULT NULL,
                    end_date DATE DEFAULT NULL,
                    status ENUM('pending', 'accepted', 'rejected') NOT NULL DEFAULT 'pending',
                    awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # company_faqs table stores FAQs specific to a company profile
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_faqs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_faqs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    job_id INT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_team (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    user_id INT NOT NULL,
                    role VARCHAR(100) DEFAULT 'Member',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_company_user (company_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    candidate_id INT NOT NULL,
                    job_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    interview_date DATETIME NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    status ENUM('scheduled', 'completed', 'cancelled') NOT NULL DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                    FOREIGN KEY (candidate_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NULL,
                    type VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    status ENUM('Pending', 'Resolved') NOT NULL DEFAULT 'Pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    admin_name VARCHAR(255) DEFAULT NULL,
                    action VARCHAR(255) NOT NULL,
                    target_type VARCHAR(255) DEFAULT NULL,
                    target_id INT DEFAULT NULL,
                    details TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    search_query VARCHAR(255) DEFAULT NULL,
                    opportunity_type VARCHAR(50) DEFAULT NULL,
                    location VARCHAR(255) DEFAULT NULL,
                    experience_level VARCHAR(255) DEFAULT NULL,
                    email_alerts TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    link VARCHAR(255) DEFAULT NULL,
                    is_read TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    follower_id INT NOT NULL,
                    followed_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (followed_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_follow (follower_id, followed_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_notes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    application_id INT NOT NULL,
                    author_id INT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_groups (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    image VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_group_members (
                    group_id INT NOT NULL,
                    user_id INT NOT NULL,
                    PRIMARY KEY (group_id, user_id),
                    FOREIGN KEY (group_id) REFERENCES community_groups(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_discussions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    category VARCHAR(100) NOT NULL,
                    author_id INT NOT NULL,
                    views INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS community_discussion_answers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    discussion_id INT NOT NULL,
                    author_id INT NOT NULL,
                    answer_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (discussion_id) REFERENCES community_discussions(id) ON DELETE CASCADE,
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
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
            ("account_type", "ALTER TABLE users ADD COLUMN account_type ENUM('individual','company','admin') NOT NULL DEFAULT 'individual'"),
            ("email_verified", "ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 0"),
            ("verification_token", "ALTER TABLE users ADD COLUMN verification_token VARCHAR(255) DEFAULT NULL"),
            ("verification_token_expires_at", "ALTER TABLE users ADD COLUMN verification_token_expires_at TIMESTAMP NULL DEFAULT NULL"),
            ("reset_password_token", "ALTER TABLE users ADD COLUMN reset_password_token VARCHAR(255) DEFAULT NULL"),
            ("reset_password_token_expires_at", "ALTER TABLE users ADD COLUMN reset_password_token_expires_at TIMESTAMP NULL DEFAULT NULL"),
            ("active_status", "ALTER TABLE users ADD COLUMN active_status ENUM('actively_looking', 'open_to_offers', 'not_looking') NOT NULL DEFAULT 'actively_looking'"),
            ("headhunting_mode", "ALTER TABLE users ADD COLUMN headhunting_mode TINYINT(1) NOT NULL DEFAULT 1"),
            ("resume_analysis", "ALTER TABLE users ADD COLUMN resume_analysis LONGTEXT DEFAULT NULL"),
            ("verified",     "ALTER TABLE users ADD COLUMN verified TINYINT(1) NOT NULL DEFAULT 0"),
            ("is_banned",    "ALTER TABLE users ADD COLUMN is_banned TINYINT(1) NOT NULL DEFAULT 0"),
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

        # Explicitly make sure ENUM list includes 'admin'
        with self.__connection.cursor() as cursor:
            cursor.execute("ALTER TABLE users MODIFY COLUMN account_type ENUM('individual', 'company', 'admin') NOT NULL DEFAULT 'individual'")

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
        if "sector" not in existing_jobs:
            with self.__connection.cursor() as cursor:
                cursor.execute("ALTER TABLE jobs ADD COLUMN sector VARCHAR(255) DEFAULT NULL")

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

        # Create user_badges if it doesn't exist (migration)
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_badges (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    company_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    badge_type ENUM('internship', 'employment', 'contribution', 'other') NOT NULL DEFAULT 'employment',
                    description TEXT DEFAULT NULL,
                    start_date DATE DEFAULT NULL,
                    end_date DATE DEFAULT NULL,
                    status ENUM('pending', 'accepted', 'rejected') NOT NULL DEFAULT 'pending',
                    awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

        # Create saved_searches if it doesn't exist (migration)
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_searches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    search_query VARCHAR(255) DEFAULT NULL,
                    opportunity_type VARCHAR(50) DEFAULT NULL,
                    location VARCHAR(255) DEFAULT NULL,
                    experience_level VARCHAR(255) DEFAULT NULL,
                    email_alerts TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        
        # Create notifications if it doesn't exist (migration)
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    link VARCHAR(255) DEFAULT NULL,
                    is_read TINYINT(1) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

        # Create follows if it doesn't exist (migration)
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS follows (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    follower_id INT NOT NULL,
                    followed_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (followed_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_follow (follower_id, followed_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

        # Notifications table migrations
        notifications_migrations = [
            ("type", "ALTER TABLE notifications ADD COLUMN type VARCHAR(50) NOT NULL DEFAULT 'general'"),
            ("link", "ALTER TABLE notifications ADD COLUMN link VARCHAR(255) DEFAULT NULL"),
        ]
        with self.__connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'notifications'",
                (config.MYSQL_DATABASE,)
            )
            existing_notifications = {row["COLUMN_NAME"] for row in cursor.fetchall()}

        for col, sql in notifications_migrations:
            if col not in existing_notifications:
                with self.__connection.cursor() as cursor:
                    cursor.execute(sql)

        # Ensure type column has a default value (fixes old schema where it was NOT NULL without default)
        if "type" in existing_notifications:
            with self.__connection.cursor() as cursor:
                cursor.execute("ALTER TABLE notifications MODIFY COLUMN type VARCHAR(50) NOT NULL DEFAULT 'general'")

        # Create company_team, interviews, application_notes migrations
        with self.__connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_team (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    user_id INT NOT NULL,
                    role VARCHAR(100) DEFAULT 'Member',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_company_user (company_id, user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interviews (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_id INT NOT NULL,
                    candidate_id INT NOT NULL,
                    job_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    interview_date DATETIME NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    status ENUM('scheduled', 'completed', 'cancelled') NOT NULL DEFAULT 'scheduled',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                    FOREIGN KEY (candidate_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS application_notes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    application_id INT NOT NULL,
                    author_id INT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
                    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)


    def get_connection(self):
        # Check if the current thread already has an active MySQL connection initialized.
        # Since Flask runs in a multithreaded environment, using thread-local storage (self._local)
        # ensures each thread/request maintains its own connection, avoiding packet sequence collisions.
        if not hasattr(self._local, "connection") or not self._local.connection:
            try:
                # Establish a fresh MySQL database connection using credentials from config.py
                self._local.connection = pymysql.connect(
                    host=config.MYSQL_HOST,
                    user=config.MYSQL_USER,
                    password=config.MYSQL_PASSWORD,
                    database=config.MYSQL_DATABASE,
                    cursorclass=pymysql.cursors.DictCursor,  # Return query results as dictionaries
                    autocommit=True,                         # Automatically commit transactions
                )
            except Exception as e:
                # Print connection error details to server logs and set connection reference to None
                print("Failed to establish database connection:", e)
                self._local.connection = None
        else:
            try:
                # Ping the existing database connection to check if it's still alive.
                # If it has disconnected, reconnect=True automatically attempts a reconnect.
                self._local.connection.ping(reconnect=True)
            except Exception:
                try:
                    # If pinging fails, manually attempt to reconnect and establish a fresh connection socket.
                    self._local.connection = pymysql.connect(
                        host=config.MYSQL_HOST,
                        user=config.MYSQL_USER,
                        password=config.MYSQL_PASSWORD,
                        database=config.MYSQL_DATABASE,
                        cursorclass=pymysql.cursors.DictCursor,
                        autocommit=True,
                    )
                except Exception as e:
                    # Log failure to reconnect and reset connection state to None
                    print("Failed to reconnect to database:", e)
                    self._local.connection = None
        # Return the thread-specific active MySQL connection object
        return self._local.connection

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
                    print("Mock events seeded successfully!")

    def _seed_mock_saved_searches(self):
        """Seed mock saved searches if the saved_searches table is empty."""
        with self.__connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM saved_searches")
            if cursor.fetchone()["cnt"] == 0:
                # Find an individual candidate to attach the saved searches to
                cursor.execute("SELECT id FROM users WHERE account_type = 'individual' LIMIT 1")
                user = cursor.fetchone()
                if user:
                    user_id = user["id"]
                    cursor.execute("""
                        INSERT INTO saved_searches (user_id, search_query, opportunity_type, location, experience_level, email_alerts)
                        VALUES 
                        (%s, 'Python', 'job', 'Kathmandu (Onsite)', 'Entry', 1),
                        (%s, 'React', 'internship', 'Remote', 'All Levels', 0)
                    """, (user_id, user_id))
                    print("Mock saved searches seeded successfully!")

    def _seed_community_data(self):
        """Seed initial community groups and discussions if they are empty."""
        with self.__connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM community_groups")
            if cursor.fetchone()["cnt"] == 0:
                cursor.execute("""
                    INSERT INTO community_groups (name, description, category, image)
                    VALUES 
                    ('Nepal Python Developers', 'A community for Python and Django enthusiasts in Nepal to share knowledge, jobs, and best practices.', 'Development', 'https://images.unsplash.com/photo-1515879218367-8466d910aaa4?q=80&w=300&auto=format&fit=crop'),
                    ('AI/ML Researchers Nepal', 'Discuss machine learning, deep learning, NLP, computer vision and share research papers and projects in Nepal.', 'AI/ML', 'https://images.unsplash.com/photo-1677442136019-21780efad99a?q=80&w=300&auto=format&fit=crop'),
                    ('Women In Tech Nepal', 'Empowering women in technology through mentorship, networking opportunities, and skill development workshops.', 'Career', 'https://images.unsplash.com/photo-1573164713988-8665fc963095?q=80&w=300&auto=format&fit=crop'),
                    ('UI/UX Designers Kathmandu', 'A group for user experience and user interface designers in Nepal to share portfolios, design trends, and feedback.', 'Design', 'https://images.unsplash.com/photo-1581291518633-83b4ebd1d83e?q=80&w=300&auto=format&fit=crop')
                """)
                print("Community groups seeded successfully!")

            cursor.execute("SELECT COUNT(*) as cnt FROM community_discussions")
            if cursor.fetchone()["cnt"] == 0:
                cursor.execute("SELECT id FROM users LIMIT 3")
                users = cursor.fetchall()
                if len(users) >= 2:
                    author1 = users[0]["id"]
                    author2 = users[1]["id"]
                    
                    cursor.execute("""
                        INSERT INTO community_discussions (title, description, category, author_id, views)
                        VALUES ('How to get started with Django/Flask in Nepals tech market?', 'I am a college student and want to learn backend development. Is Django or Flask more popular for entry level jobs in Nepal? What are the key skills companies look for?', 'Career', %s, 120)
                    """, (author1,))
                    disc1_id = cursor.lastrowid

                    cursor.execute("""
                        INSERT INTO community_discussions (title, description, category, author_id, views)
                        VALUES ('Is Tailwind CSS preferred over Vanilla CSS for modern web projects?', 'Our team is starting a new project. I prefer Vanilla CSS for design freedom, but everyone else wants Tailwind CSS for speed. What are your experiences with project maintenance?', 'Development', %s, 340)
                    """, (author2,))
                    disc2_id = cursor.lastrowid
                    
                    cursor.execute("""
                        INSERT INTO community_discussion_answers (discussion_id, author_id, answer_text)
                        VALUES 
                        (%s, %s, 'Django is definitely more popular in Nepal because many development shops build larger enterprise applications. Flask is great for learning concepts though!'),
                        (%s, %s, 'I suggest starting with Flask to understand how routing and request-response works, then moving to Django for its out-of-the-box features like admin panel and ORM.'),
                        (%s, %s, 'For fast scaling, Tailwind is a life saver. If you have unique designs, vanilla CSS or CSS modules is cleaner.')
                    """, (disc1_id, author2, disc1_id, author1, disc2_id, author1))
                    print("Community discussions and answers seeded successfully!")

