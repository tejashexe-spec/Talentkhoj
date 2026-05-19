import os

from flask import Flask, flash, redirect, render_template, request, url_for
import pymysql
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-sprint-secret")
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "localhost")
app.config["MYSQL_PORT"] = int(os.environ.get("MYSQL_PORT", "3306"))
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "Prish_123")
app.config["MYSQL_DATABASE"] = os.environ.get("MYSQL_DATABASE", "talent_khoj")


def get_db_connection():
    return pymysql.connect(
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def init_db():
    # Connect without specifying the database so we can create it if it is missing
    connection = pymysql.connect(
        host=app.config["MYSQL_HOST"],
        port=app.config["MYSQL_PORT"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{app.config['MYSQL_DATABASE']}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE `{app.config['MYSQL_DATABASE']}`")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    full_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
    finally:
        connection.close()


def find_user_by_email(email):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, full_name, email, password_hash, created_at FROM users WHERE email = %s",
                (email,),
            )
            return cursor.fetchone()
    finally:
        connection.close()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    form_data = {"full_name": "", "email": ""}
    errors = {}

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form_data = {"full_name": full_name, "email": email}

        if not full_name:
            errors["full_name"] = "Full name is required."

        if not email or "@" not in email:
            errors["email"] = "Enter a valid email address."

        if len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."

        if password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        if email and find_user_by_email(email) is not None:
            errors["email"] = "An account with that email already exists."

        if not errors:
            password_hash = generate_password_hash(password)

            connection = get_db_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
                        (full_name, email, password_hash),
                    )
            finally:
                connection.close()

            flash("Registration saved.", "success")
            return redirect(url_for("home"))

    return render_template("register.html", form_data=form_data, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    form_data = {"email": ""}
    message = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        form_data = {"email": email}

        user = find_user_by_email(email) if email else None
        if user is not None and check_password_hash(user["password_hash"], password):
            message = f"Login check passed for {user['full_name']}."
        else:
            message = "Invalid email or password."

    return render_template("login.html", form_data=form_data, message=message)

if os.environ.get("INITIALIZE_MYSQL_SCHEMA", "1") == "1":
    try:
        init_db()
    except pymysql.MySQLError as exc:
        app.logger.warning("Skipping MySQL schema initialization: %s", exc)


if __name__ == "__main__":
    app.run(debug=True)