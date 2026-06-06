import sys
import os
import time
import secrets
from datetime import datetime, timedelta
from functools import wraps
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from my_first_flask import config
from my_first_flask.model.database import Database
from my_first_flask.services.email_service import EmailService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

app.secret_key = config.SECRET_KEY

# ── Google OAuth ──────────────────────────────────────────────────────────────
oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=config.GOOGLE_CLIENT_ID,
    client_secret=config.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# Initialize database once
db = Database()


@app.context_processor
def inject_session():
    return dict(session=session)
def get_db():
    return db.get_connection()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ─── HOME ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html")


# ─── REGISTER ────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    form_data = {"full_name": "", "email": "", "account_type": "individual",
                 "company_name": "", "company_address": "", "pan_number": "", "company_email": ""}
    errors = {}

    if request.method == "POST":
        account_type = request.form.get("account_type", "individual")
        if account_type not in ("individual", "company"):
            account_type = "individual"
        form_data["account_type"] = account_type

        if account_type == "individual":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            form_data.update({"full_name": full_name, "email": email})

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
                        "INSERT INTO users (full_name, email, password_hash, account_type) VALUES (%s, %s, %s, 'individual')",
                        (full_name, email, password_hash)
                    )
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))

        else:  # company
            company_name = request.form.get("company_name", "").strip()
            company_address = request.form.get("company_address", "").strip()
            pan_number = request.form.get("pan_number", "").strip()
            company_email = request.form.get("company_email", "").strip().lower()
            password = request.form.get("company_password", "")
            confirm_password = request.form.get("company_confirm_password", "")

            form_data.update({
                "company_name": company_name,
                "company_address": company_address,
                "pan_number": pan_number,
                "company_email": company_email
            })

            if not company_name:
                errors["company_name"] = "Company name is required."
            if not company_address:
                errors["company_address"] = "Company address is required."
            if not company_email or "@" not in company_email:
                errors["company_email"] = "Enter a valid email address."
            if len(password) < 8:
                errors["company_password"] = "Password must be at least 8 characters."
            if password != confirm_password:
                errors["company_confirm_password"] = "Passwords do not match."

            if not errors:
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE email = %s", (company_email,))
                    if cursor.fetchone():
                        errors["company_email"] = "An account with that email already exists."

            if not errors:
                password_hash = generate_password_hash(password)
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO users (full_name, email, password_hash, account_type) VALUES (%s, %s, %s, 'company')",
                        (company_name, company_email, password_hash)
                    )
                    user_id = cursor.lastrowid
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO companies (user_id, company_name, address, pan_number) VALUES (%s, %s, %s, %s)",
                        (user_id, company_name, company_address, pan_number or None)
                    )
                flash("Company registered successfully. Please log in.", "success")
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
                    "SELECT id, full_name, email, password_hash, avatar, account_type FROM users WHERE email = %s",
                    (email,)
                )
                user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_email"] = user["email"]
                session["user_avatar"] = user["avatar"]
                session["account_type"] = user["account_type"]
                return redirect(url_for("home"))
            else:
                error = "Invalid email or password."

    return render_template("login.html", form_data=form_data, error=error)


@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, full_name, email_verified FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
        
        if user and not user["email_verified"]:
            verification_token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=24)
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET verification_token = %s, verification_token_expires_at = %s WHERE id = %s",
                    (verification_token, expires_at, user["id"])
                )
            
            verification_link = url_for("verify_email_callback", token=verification_token, _external=True)
            email_html = f"""
            <p>Hi {user['full_name']},</p>
            <p>Please click the link below to verify your email address:</p>
            <p><a href="{verification_link}">{verification_link}</a></p>
            <p>This link will expire in 24 hours.</p>
            """
            
            EmailService.send_email(
                to=email,
                subject="Verify Your Email - Talent Khoj",
                html=email_html
            )
            
            flash("Verification link sent to your email!", "success")
            return redirect(url_for("login"))
        elif user and user["email_verified"]:
            flash("Your email is already verified!", "info")
            return redirect(url_for("login"))
        else:
            flash("No account found with that email.", "error")
    
    return render_template("verify_email.html")


@app.route("/verify-email/<token>")
def verify_email_callback(token):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, verification_token_expires_at FROM users WHERE verification_token = %s",
            (token,)
        )
        user = cursor.fetchone()
    
    if user:
        if user["verification_token_expires_at"] > datetime.utcnow():
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET email_verified = TRUE, verification_token = NULL, verification_token_expires_at = NULL WHERE id = %s",
                    (user["id"],)
                )
            flash("Email verified successfully! Please log in.", "success")
        else:
            flash("Verification link has expired. Please request a new one.", "error")
    else:
        flash("Invalid verification link.", "error")
    
    return redirect(url_for("login"))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, full_name FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
        
        if user:
            reset_token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=1)
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET reset_password_token = %s, reset_password_token_expires_at = %s WHERE id = %s",
                    (reset_token, expires_at, user["id"])
                )
            
            reset_link = url_for("reset_password_callback", token=reset_token, _external=True)
            email_html = f"""
            <p>Hi {user['full_name']},</p>
            <p>Please click the link below to reset your password:</p>
            <p><a href="{reset_link}">{reset_link}</a></p>
            <p>This link will expire in 1 hour.</p>
            """
            
            EmailService.send_email(
                to=email,
                subject="Reset Your Password - Talent Khoj",
                html=email_html
            )
            
            flash("Password reset link sent to your email!", "success")
            return redirect(url_for("login"))
        else:
            flash("No account found with that email.", "error")
    
    return render_template("reset_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_callback(token):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, reset_password_token_expires_at FROM users WHERE reset_password_token = %s",
            (token,)
        )
        user = cursor.fetchone()
    
    if not user or user["reset_password_token_expires_at"] < datetime.utcnow():
        flash("Password reset link is invalid or has expired.", "error")
        return redirect(url_for("reset_password"))
    
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if len(new_password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif new_password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            password_hash = generate_password_hash(new_password)
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET password_hash = %s, reset_password_token = NULL, reset_password_token_expires_at = NULL WHERE id = %s",
                    (password_hash, user["id"])
                )
            flash("Password reset successfully! Please log in.", "success")
            return redirect(url_for("login"))
    
    return render_template("reset_password_confirm.html", token=token)


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


# ─── PUBLIC PROFILES ─────────────────────────────────────────────────────────

@app.route("/user/<int:user_id>")
def user_profile(user_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, full_name, avatar, bio, location, skills, cv_path FROM users WHERE id = %s AND account_type = 'individual'",
            (user_id,)
        )
        user = cursor.fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("home"))
    return render_template("user_profile.html", user=user)


@app.route("/company/<int:user_id>")
def company_profile(user_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT c.*, u.id as user_id FROM companies c JOIN users u ON c.user_id = u.id WHERE c.user_id = %s",
            (user_id,)
        )
        company = cursor.fetchone()
    if not company:
        flash("Company not found.", "error")
        return redirect(url_for("home"))
    return render_template("company_profile.html", company=company)


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


@app.route("/dashboard/events")
@login_required
def dashboard_events():
    return render_template("dashboard_events.html")


@app.route("/dashboard/events/create", methods=["GET", "POST"])
@login_required
def dashboard_create_event():
    if session.get("account_type") != "company":
        return redirect(url_for("dashboard_events"))
    return render_template("dashboard_create_event.html")


@app.route("/dashboard/post-opportunity")
@login_required
def dashboard_post_opportunity():
    if session.get("account_type") != "company":
        return redirect(url_for("dashboard"))
    return render_template("dashboard_post_opportunity.html")


# ── Google OAuth ──────────────────────────────────────────────────────────────

@app.route("/login/google")
def google_login():
    redirect_uri = "http://127.0.0.1:5000/login/google/callback"
    print(f"Using hardcoded redirect URI: {redirect_uri}")
    return google.authorize_redirect(redirect_uri)


@app.route("/login/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get("userinfo")

    if not user_info:
        flash("Google login failed. Please try again.", "error")
        return redirect(url_for("login"))

    email = user_info["email"]
    full_name = user_info.get("name", email.split("@")[0].capitalize())
    avatar = user_info.get("picture")

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, full_name, avatar, account_type FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

    if not user:
        # New Google user — store info in session and ask them to choose account type
        session["google_pending"] = {
            "email": email,
            "full_name": full_name,
            "avatar": avatar
        }
        return redirect(url_for("select_account_type"))

    # Existing user — log them in directly
    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["user_email"] = email
    session["user_avatar"] = user.get("avatar") or avatar
    session["account_type"] = user["account_type"]
    return redirect(url_for("home"))


@app.route("/select-account-type", methods=["GET", "POST"])
def select_account_type():
    # Only accessible after Google OAuth for new users
    if not session.get("google_pending"):
        return redirect(url_for("login"))

    errors = {}
    pending = session["google_pending"]

    if request.method == "POST":
        account_type = request.form.get("account_type", "individual")
        company_name = request.form.get("company_name", "").strip()
        company_address = request.form.get("company_address", "").strip()
        pan_number = request.form.get("pan_number", "").strip()

        if account_type == "company":
            if not company_name:
                errors["company_name"] = "Company name is required."
            if not company_address:
                errors["company_address"] = "Company address is required."

        if not errors:
            password_hash = generate_password_hash(secrets.token_hex(32))
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (full_name, email, password_hash, avatar, account_type) VALUES (%s, %s, %s, %s, %s)",
                    (pending["full_name"], pending["email"], password_hash, pending["avatar"], account_type)
                )
                user_id = cursor.lastrowid

            if account_type == "company":
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO companies (user_id, company_name, address, pan_number) VALUES (%s, %s, %s, %s)",
                        (user_id, company_name, company_address, pan_number or None)
                    )

            session.pop("google_pending", None)
            session["user_id"] = user_id
            session["user_name"] = pending["full_name"]
            session["user_email"] = pending["email"]
            session["user_avatar"] = pending["avatar"]
            session["account_type"] = account_type
            return redirect(url_for("home"))

    return render_template("select_account_type.html", errors=errors)


if __name__ == "__main__":
    app.run(debug=True)
