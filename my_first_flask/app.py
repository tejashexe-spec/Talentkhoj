import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from my_first_flask import config
from my_first_flask.model.database import Database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

app.secret_key = config.SECRET_KEY

# Initialize database once
db = Database()


@app.context_processor
def inject_session():
    return dict(session=session)


def get_db():
    return db.get_connection()


# ─── HOME ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    features = [
        {
            "icon": "📈",
            "title": "Candidate Pulse",
            "description": "AI-driven insights matching your skills to the perfect role instantly.",
            "tag": None
        },
        {
            "icon": "👥",
            "title": "Community Layer",
            "description": "Connect with mentors, peers, and industry leaders in Nepal.",
            "tag": None
        },
        {
            "icon": "</>",
            "title": "Frontend Developer Intern",
            "description": "TechFlow Nepal",
            "tag": "NEW"
        },
    ]
    return render_template("home.html", features=features)


# ─── REGISTER ────────────────────────────────────────────────────────────────

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

        if not errors:
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    errors["email"] = "An account with that email already exists."

        if not errors:
            password_hash = generate_password_hash(password)
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
                    (full_name, email, password_hash)
                )
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html", form_data=form_data, errors=errors)


# ─── LOGIN ───────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))

    form_data = {"email": ""}
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        form_data = {"email": email}

        if not email or not password:
            error = "Please enter your email and password."
        else:
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, full_name, email, password_hash, avatar FROM users WHERE email = %s",
                    (email,)
                )
                user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_email"] = user["email"]
                session["user_avatar"] = user["avatar"]
                return redirect(url_for("home"))
            else:
                error = "Invalid email or password."

    return render_template("login.html", form_data=form_data, error=error)


# ─── LOGOUT ──────────────────────────────────────────────────────────────────

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ─── PROFILE ─────────────────────────────────────────────────────────────────

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    name_message = None
    password_message = None
    password_errors = []

    if request.method == "POST":
        action = request.form.get("action")

        # ── Change Name ──────────────────────────────────────────────────────
        if action == "change_name":
            full_name = request.form.get("full_name", "").strip()
            if not full_name:
                name_message = "Name cannot be empty."
            else:
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET full_name = %s WHERE id = %s",
                        (full_name, session["user_id"])
                    )
                session["user_name"] = full_name
                session.modified = True
                name_message = "Name updated successfully."

        # ── Change Password ──────────────────────────────────────────────────
        elif action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT password_hash FROM users WHERE id = %s",
                    (session["user_id"],)
                )
                user = cursor.fetchone()

            if not user or not check_password_hash(user["password_hash"], current_password):
                password_errors.append("Current password is incorrect.")
            if len(new_password) < 8:
                password_errors.append("New password must be at least 8 characters.")
            if new_password != confirm_password:
                password_errors.append("Passwords do not match.")

            if not password_errors:
                new_hash = generate_password_hash(new_password)
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET password_hash = %s WHERE id = %s",
                        (new_hash, session["user_id"])
                    )
                password_message = "Password updated successfully."

        # ── Upload Avatar ────────────────────────────────────────────────────
        elif action == "upload_avatar":
            avatar = request.files.get("avatar")
            allowed = {"png", "jpg", "jpeg", "gif", "webp"}
            if avatar and avatar.filename:
                ext = avatar.filename.rsplit(".", 1)[-1].lower()
                if ext in allowed:
                    filename = f"user_{session['user_id']}_{int(time.time())}.{ext}"
                    upload_path = os.path.join(BASE_DIR, "static", "uploads", filename)
                    avatar.save(upload_path)
                    avatar_url = f"/static/uploads/{filename}"

                    conn = get_db()
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE users SET avatar = %s WHERE id = %s",
                            (avatar_url, session["user_id"])
                        )
                    session["user_avatar"] = avatar_url
                    session.modified = True
                else:
                    name_message = "Invalid file type. Use PNG, JPG, GIF or WEBP."

    return render_template("profile.html",
        name_message=name_message,
        password_message=password_message,
        password_errors=password_errors
    )


# ─── STATIC PAGES ────────────────────────────────────────────────────────────

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ─── DASHBOARD ───────────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/dashboard/search")
@login_required
def dashboard_search():
    return render_template("dashboard_search.html")


@app.route("/dashboard/applications")
@login_required
def dashboard_applications():
    return render_template("dashboard_applications.html")


@app.route("/dashboard/saved")
@login_required
def dashboard_saved():
    return render_template("dashboard_saved.html")


@app.route("/dashboard/inbox")
@login_required
def dashboard_inbox():
    return render_template("dashboard_inbox.html")


@app.route("/dashboard/settings")
@login_required
def dashboard_settings():
    return render_template("dashboard_settings.html")


if __name__ == "__main__":
    app.run(debug=True)
