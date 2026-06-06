import sys
import os
import time
import secrets
from datetime import datetime, timedelta
from functools import wraps
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail, Message
from my_first_flask import config
from my_first_flask.model.database import Database
from my_first_flask.services.email_service import EmailService

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

app.secret_key = config.SECRET_KEY
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# ── Flask-Mail ────────────────────────────────────────────────────────────────
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_SSL'] = config.MAIL_USE_SSL
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD
mail = Mail(app)

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


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id") or session.get("account_type") != "admin":
            flash("Unauthorized access. Admin privileges required.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ─── HOME ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(BASE_DIR, "static", "favicon.png"), mimetype="image/png")



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
                    "SELECT id, full_name, email, password_hash, avatar, account_type, is_banned, ban_reason FROM users WHERE email = %s",
                    (email,)
                )
                user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                if user.get("is_banned"):
                    reason = user.get("ban_reason") or "Contact support for more information."
                    error = f"Your account has been suspended. Reason: {reason}"
                else:
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

        # ── About Details ───────────────────────────────────────────────────
        if action == "about":
            first_name = request.form.get("first_name", "").strip()
            last_name = request.form.get("last_name", "").strip()
            gender = request.form.get("gender", "").strip()
            dob = request.form.get("dob", "").strip()
            sectors = request.form.get("sectors", "").strip()
            designation = request.form.get("designation", "").strip()
            bio = request.form.get("bio", "").strip()
            
            full_name = f"{first_name} {last_name}".strip()
            
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT cv_data FROM users WHERE id = %s", (session["user_id"],))
                row = cursor.fetchone()
            
            import json
            try:
                cv_data = json.loads(row["cv_data"]) if row and row.get("cv_data") else {}
            except Exception:
                cv_data = {}
                
            cv_data["first_name"] = first_name
            cv_data["last_name"] = last_name
            cv_data["gender"] = gender
            cv_data["dob"] = dob
            cv_data["sectors"] = sectors
            cv_data["designation"] = designation
            cv_data["bio"] = bio
            cv_data["full_name"] = full_name
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET full_name = %s, bio = %s, cv_data = %s WHERE id = %s",
                    (full_name, bio, json.dumps(cv_data), session["user_id"])
                )
            session["user_name"] = full_name
            session.modified = True
            name_message = "About details updated successfully."

        # ── Address Details ──────────────────────────────────────────────────
        elif action == "address":
            province = request.form.get("province", "").strip()
            city = request.form.get("city", "").strip()
            postal_code = request.form.get("postal_code", "").strip()
            current_address = request.form.get("current_address", "").strip()
            
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT cv_data FROM users WHERE id = %s", (session["user_id"],))
                row = cursor.fetchone()
            
            import json
            try:
                cv_data = json.loads(row["cv_data"]) if row and row.get("cv_data") else {}
            except Exception:
                cv_data = {}
                
            cv_data["province"] = province
            cv_data["city"] = city
            cv_data["postal_code"] = postal_code
            cv_data["current_address"] = current_address
            cv_data["location"] = f"{city}, {province}"
            
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET location = %s, cv_data = %s WHERE id = %s",
                    (f"{city}, {province}", json.dumps(cv_data), session["user_id"])
                )
            name_message = "Address details updated successfully."

        # ── Social Links ─────────────────────────────────────────────────────
        elif action == "socials":
            social_types = request.form.getlist("social_type[]")
            social_links = request.form.getlist("social_link[]")
            
            socials_list = []
            portfolio_link = ""
            github_link = ""
            linkedin_link = ""
            
            for i in range(len(social_types)):
                t = social_types[i].strip()
                l = social_links[i].strip()
                if t and l:
                    socials_list.append({"type": t, "link": l})
                    if t.lower() == "portfolio":
                        portfolio_link = l
                    elif t.lower() == "github":
                        github_link = l
                    elif t.lower() == "linkedin":
                        linkedin_link = l
            
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT cv_data FROM users WHERE id = %s", (session["user_id"],))
                row = cursor.fetchone()
            
            import json
            try:
                cv_data = json.loads(row["cv_data"]) if row and row.get("cv_data") else {}
            except Exception:
                cv_data = {}
                
            cv_data["socials"] = socials_list
            if portfolio_link:
                cv_data["portfolio"] = portfolio_link
            if github_link:
                cv_data["github"] = github_link
            if linkedin_link:
                cv_data["linkedin"] = linkedin_link
                
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET cv_data = %s WHERE id = %s",
                    (json.dumps(cv_data), session["user_id"])
                )
            name_message = "Social links updated successfully."

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

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        user_profile = cursor.fetchone()

    if user_profile and user_profile.get("cv_data"):
        import json
        try:
            cv_data = json.loads(user_profile["cv_data"])
            if isinstance(cv_data, dict):
                for k, v in cv_data.items():
                    if k not in user_profile or user_profile[k] is None:
                        user_profile[k] = v
        except Exception:
            pass

    return render_template("profile.html",
        profile=user_profile,
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
    conn = get_db()
    stats = {}
    my_opportunities = []
    
    if session.get("account_type") == "company":
        with conn.cursor() as cursor:
            # Get company details
            cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
            company = cursor.fetchone()
            
            if company:
                # Fetch posted jobs
                cursor.execute("""
                    SELECT id, title, opportunity_type, location, salary, created_at 
                    FROM jobs 
                    WHERE company_id = %s 
                    ORDER BY created_at DESC
                """, (company["id"],))
                my_opportunities = cursor.fetchall()
                stats["posted_count"] = len(my_opportunities)
    else:
        # Candidate metrics
        with conn.cursor() as cursor:
            # 1. Has CV
            cursor.execute("SELECT cv_path FROM users WHERE id = %s", (session["user_id"],))
            user = cursor.fetchone()
            stats["has_cv"] = bool(user and user["cv_path"])
            
            # 2. Applied Count
            cursor.execute("SELECT COUNT(*) as count FROM applications WHERE user_id = %s", (session["user_id"],))
            stats["applied_count"] = cursor.fetchone()["count"]
            
            # 3. Rejected Count
            cursor.execute("SELECT COUNT(*) as count FROM applications WHERE user_id = %s AND status = 'rejected'", (session["user_id"],))
            stats["rejected_count"] = cursor.fetchone()["count"]
            
            # 4. Total Jobs (Alerts)
            cursor.execute("SELECT COUNT(*) as count FROM jobs")
            stats["alerts_count"] = cursor.fetchone()["count"]
            
            # 5. Bookmarks
            stats["bookmarks_count"] = 0
            
            # 6. Recent Applications
            cursor.execute("""
                SELECT j.id as job_id, j.title, j.location, j.opportunity_type, a.status, a.created_at
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.user_id = %s
                ORDER BY a.created_at DESC
                LIMIT 5
            """, (session["user_id"],))
            recent_applications = cursor.fetchall()
            
            # 7. Activities
            cursor.execute("SELECT cv_path, cv_data FROM users WHERE id = %s", (session["user_id"],))
            ud = cursor.fetchone()
            activities = []
            if ud:
                activities.append({
                    "title": "Account created",
                    "description": f"{session['user_name']} | {session.get('user_email', '')}",
                    "time": "Joined"
                })
                if ud.get("cv_path"):
                    activities.append({
                        "title": "Resume active",
                        "description": "Professional CV is online and ready for recruitment",
                        "time": "Active"
                    })
                
            cursor.execute("""
                SELECT j.title, a.status, a.created_at
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.user_id = %s
                ORDER BY a.created_at DESC
                LIMIT 6
            """, (session["user_id"],))
            user_apps = cursor.fetchall()
            for app in user_apps:
                activities.append({
                    "title": f"Applied to {app['title']}",
                    "description": f"{session['user_name']} | {session.get('user_email', '')}",
                    "time": app["created_at"].strftime("%Y-%m-%d %H:%M")
                })
                if app["status"] != "applied":
                    activities.append({
                        "title": f"Application status changed to {app['status'].upper()}",
                        "description": f"Update on role: {app['title']}",
                        "time": "Recent"
                    })
            
        return render_template("dashboard.html", 
                               stats=stats, 
                               recent_applications=recent_applications, 
                               activities=activities)



@app.route("/dashboard/ats")
@login_required
def dashboard_ats():
    if session.get("account_type") != "company":
        flash("Only company accounts can access the ATS Board.", "error")
        return redirect(url_for("dashboard"))
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        flash("Please complete your company profile first.", "error")
        return redirect(url_for("profile"))
        
    company_id = company["id"]
    
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, title FROM jobs WHERE company_id = %s ORDER BY created_at DESC", (company_id,))
        jobs = cursor.fetchall()
        
    selected_job_id = request.args.get("job_id", "").strip()
    skill_filter = request.args.get("skills", "").strip()
    location_filter = request.args.get("location", "").strip()
    experience_filter = request.args.get("experience", "").strip()
    
    query = """
        SELECT a.id as application_id, a.status, a.answers, a.created_at as applied_at,
               u.id as user_id, u.full_name, u.email, u.avatar, u.location, u.skills, u.cv_path, u.cv_data,
               j.id as job_id, j.title as job_title
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN users u ON a.user_id = u.id
        WHERE j.company_id = %s
    """
    params = [company_id]
    
    if selected_job_id:
        query += " AND a.job_id = %s"
        params.append(selected_job_id)
        
    query += " ORDER BY a.created_at DESC"
    
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        all_apps = cursor.fetchall()
        
    import json
    filtered_apps = []
    
    for app in all_apps:
        cv_data = {}
        if app.get("cv_data"):
            try:
                cv_data = json.loads(app["cv_data"])
            except Exception:
                pass
                
        answers_list = []
        if app.get("answers"):
            try:
                answers_list = json.loads(app["answers"])
            except Exception:
                pass
        app["answers_list"] = answers_list
        
        if skill_filter:
            skill_term = skill_filter.lower()
            in_db_skills = (app.get("skills") or "").lower()
            cv_skills = cv_data.get("skills", [])
            in_cv_skills = " ".join([s.get("category", "") + " " + s.get("list", "") for s in cv_skills]).lower()
            
            if skill_term not in in_db_skills and skill_term not in in_cv_skills:
                continue
                
        if location_filter:
            loc_term = location_filter.lower()
            in_db_loc = (app.get("location") or "").lower()
            in_cv_city = cv_data.get("city", "").lower()
            in_cv_prov = cv_data.get("province", "").lower()
            
            if loc_term not in in_db_loc and loc_term not in in_cv_city and loc_term not in in_cv_prov:
                continue
                
        if experience_filter:
            exp_term = experience_filter.lower()
            designation = cv_data.get("designation", "").lower()
            bio = (app.get("bio") or "").lower()
            cv_exp = cv_data.get("experience", [])
            exp_details = " ".join([e.get("title", "") + " " + e.get("description", "") for e in cv_exp]).lower()
            combined_exp_text = f"{designation} {bio} {exp_details}"
            
            if exp_term not in combined_exp_text:
                continue

        app_skills = []
        if app.get("skills"):
            app_skills = [s.strip() for s in app["skills"].split(",") if s.strip()]
        elif cv_data.get("skills"):
            for category in cv_data["skills"]:
                if category.get("list"):
                    app_skills.extend([s.strip() for s in category["list"].split(",") if s.strip()])
        app["skills_list"] = app_skills[:4]
        
        edu_tag = ""
        if cv_data.get("education"):
            edu_tag = cv_data["education"][0].get("degree", "")
        app["education_tag"] = edu_tag
        
        exp_tag = ""
        if cv_data.get("experience"):
            exp_tag = cv_data["experience"][0].get("title", "")
        app["experience_tag"] = exp_tag
        
        # Format datetime to string for JSON serialization
        if app.get("applied_at"):
            app["applied_at"] = app["applied_at"].strftime("%Y-%m-%d %H:%M")
            
        filtered_apps.append(app)
        
    board = {
        "applied": [],
        "reviewed": [],
        "shortlisted": [],
        "rejected": []
    }
    
    for app in filtered_apps:
        status = app["status"]
        if status in board:
            board[status].append(app)
        else:
            board["applied"].append(app)
            
    counts = {k: len(v) for k, v in board.items()}
    
    return render_template(
        "dashboard_ats.html",
        board=board,
        counts=counts,
        jobs=jobs,
        selected_job_id=selected_job_id,
        filters={
            "skills": skill_filter,
            "location": location_filter,
            "experience": experience_filter
        }
    )


@app.route("/dashboard/ats/filter")
@login_required
def dashboard_ats_filter():
    if session.get("account_type") != "company":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        return jsonify({"success": False, "message": "Company profile incomplete."})
        
    company_id = company["id"]
    
    selected_job_id = request.args.get("job_id", "").strip()
    skill_filter = request.args.get("skills", "").strip()
    location_filter = request.args.get("location", "").strip()
    experience_filter = request.args.get("experience", "").strip()
    
    query = """
        SELECT a.id as application_id, a.status, a.answers, a.created_at as applied_at,
               u.id as user_id, u.full_name, u.email, u.avatar, u.location, u.skills, u.cv_path, u.cv_data,
               j.id as job_id, j.title as job_title
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN users u ON a.user_id = u.id
        WHERE j.company_id = %s
    """
    params = [company_id]
    
    if selected_job_id:
        query += " AND a.job_id = %s"
        params.append(selected_job_id)
        
    query += " ORDER BY a.created_at DESC"
    
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        all_apps = cursor.fetchall()
        
    import json
    filtered_apps = []
    
    for app in all_apps:
        cv_data = {}
        if app.get("cv_data"):
            try:
                cv_data = json.loads(app["cv_data"])
            except Exception:
                pass
                
        answers_list = []
        if app.get("answers"):
            try:
                answers_list = json.loads(app["answers"])
            except Exception:
                pass
        app["answers_list"] = answers_list
        
        if skill_filter:
            skill_term = skill_filter.lower()
            in_db_skills = (app.get("skills") or "").lower()
            cv_skills = cv_data.get("skills", [])
            in_cv_skills = " ".join([s.get("category", "") + " " + s.get("list", "") for s in cv_skills]).lower()
            
            if skill_term not in in_db_skills and skill_term not in in_cv_skills:
                continue
                
        if location_filter:
            loc_term = location_filter.lower()
            in_db_loc = (app.get("location") or "").lower()
            in_cv_city = cv_data.get("city", "").lower()
            in_cv_prov = cv_data.get("province", "").lower()
            
            if loc_term not in in_db_loc and loc_term not in in_cv_city and loc_term not in in_cv_prov:
                continue
                
        if experience_filter:
            exp_term = experience_filter.lower()
            designation = cv_data.get("designation", "").lower()
            bio = (app.get("bio") or "").lower()
            cv_exp = cv_data.get("experience", [])
            exp_details = " ".join([e.get("title", "") + " " + e.get("description", "") for e in cv_exp]).lower()
            combined_exp_text = f"{designation} {bio} {exp_details}"
            
            if exp_term not in combined_exp_text:
                continue

        app_skills = []
        if app.get("skills"):
            app_skills = [s.strip() for s in app["skills"].split(",") if s.strip()]
        elif cv_data.get("skills"):
            for category in cv_data["skills"]:
                if category.get("list"):
                    app_skills.extend([s.strip() for s in category["list"].split(",") if s.strip()])
        app["skills_list"] = app_skills[:4]
        
        edu_tag = ""
        if cv_data.get("education"):
            edu_tag = cv_data["education"][0].get("degree", "")
        app["education_tag"] = edu_tag
        
        exp_tag = ""
        if cv_data.get("experience"):
            exp_tag = cv_data["experience"][0].get("title", "")
        app["experience_tag"] = exp_tag
        
        # Format datetime to string for JSON serialization
        if app.get("applied_at"):
            app["applied_at"] = app["applied_at"].strftime("%Y-%m-%d %H:%M")
        
        filtered_apps.append(app)
        
    return jsonify({"success": True, "applicants": filtered_apps})


@app.route("/dashboard/ats/update-status", methods=["POST"])
@login_required
def dashboard_ats_update_status():
    if session.get("account_type") != "company":
        return jsonify({"success": False, "message": "Unauthorized access."}), 403
        
    data = request.get_json() or {}
    app_id = data.get("application_id")
    new_status = data.get("status")
    
    if not app_id or not new_status:
        return jsonify({"success": False, "message": "Missing application_id or status."}), 400
        
    allowed_statuses = {"applied", "reviewed", "shortlisted", "rejected"}
    if new_status not in allowed_statuses:
        return jsonify({"success": False, "message": "Invalid status value."}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        return jsonify({"success": False, "message": "Complete your company profile first."}), 400
        
    company_id = company["id"]
    
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT a.id, a.user_id, u.full_name, j.title as job_title 
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            JOIN users u ON a.user_id = u.id
            WHERE a.id = %s AND j.company_id = %s
        """, (app_id, company_id))
        application = cursor.fetchone()
        
    if not application:
        return jsonify({"success": False, "message": "Application not found or unauthorized."}), 404
        
    with conn.cursor() as cursor:
        cursor.execute("UPDATE applications SET status = %s WHERE id = %s", (new_status, app_id))
        
    try:
        from my_first_flask.utils.logger import log_activity
        log_activity("ATS Update", f"Applicant '{application['full_name']}' (ID: {application['user_id']}) moved to '{new_status}' for job '{application['job_title']}' by Company (ID: {company_id})")
    except Exception as e:
        print(f"Failed to log activity: {e}")
        
    return jsonify({"success": True, "message": f"Applicant moved to {new_status} successfully."})


@app.route("/dashboard/search")
@login_required
def dashboard_search():
    conn = get_db()
    
    keyword = request.args.get("q", "").strip()
    opp_type = request.args.get("type", "").strip()
    location = request.args.get("location", "").strip()
    experience = request.args.get("experience", "").strip()
    
    # Fetch unique locations and experience levels for the dropdowns
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT location FROM jobs WHERE location IS NOT NULL AND location != '' ORDER BY location")
        locations = [row["location"] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT experience_level FROM jobs WHERE experience_level IS NOT NULL AND experience_level != '' ORDER BY experience_level")
        experience_levels = [row["experience_level"] for row in cursor.fetchall()]

    query = """
        SELECT j.*, c.company_name, c.logo 
        FROM jobs j
        JOIN companies c ON j.company_id = c.id
        WHERE 1=1
    """
    params = []
    
    if keyword:
        query += " AND (j.title LIKE %s OR j.description LIKE %s OR j.skills_required LIKE %s)"
        like_keyword = f"%{keyword}%"
        params.extend([like_keyword, like_keyword, like_keyword])
        
    if opp_type:
        query += " AND j.opportunity_type = %s"
        params.append(opp_type)
        
    if location:
        query += " AND j.location = %s"
        params.append(location)
        
    if experience:
        query += " AND j.experience_level = %s"
        params.append(experience)
        
    query += " ORDER BY j.created_at DESC"
    
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        opportunities = cursor.fetchall()
        
    # Get applied job IDs for current candidate
    applied_job_ids = []
    profile_complete = False
    if session.get("account_type") == "individual":
        with conn.cursor() as cursor:
            cursor.execute("SELECT job_id FROM applications WHERE user_id = %s", (session["user_id"],))
            applied_job_ids = {row["job_id"] for row in cursor.fetchall()}
            
            cursor.execute("SELECT cv_path FROM users WHERE id = %s", (session["user_id"],))
            user_profile = cursor.fetchone()
            profile_complete = bool(user_profile and user_profile.get("cv_path"))

    # Also parse skills_required and questions for each job
    import json
    for opp in opportunities:
        opp["already_applied"] = opp["id"] in applied_job_ids
        if opp.get("skills_required"):
            opp["skills_list"] = [s.strip() for s in opp["skills_required"].split(",") if s.strip()]
        else:
            opp["skills_list"] = []
            
        if opp.get("questions"):
            try:
                opp["questions_list"] = json.loads(opp["questions"])
            except Exception:
                opp["questions_list"] = []
        else:
            opp["questions_list"] = []
            
    return render_template(
        "dashboard_search.html",
        opportunities=opportunities,
        locations=locations,
        experience_levels=experience_levels,
        profile_complete=profile_complete,
        filters={
            "q": keyword,
            "type": opp_type,
            "location": location,
            "experience": experience
        }
    )
@app.route("/dashboard/apply/<int:job_id>", methods=["POST"])
@login_required
def dashboard_apply(job_id):
    if session.get("account_type") != "individual":
        return jsonify({"success": False, "message": "Only candidate accounts can apply for opportunities."}), 403
        
    conn = get_db()
    with conn.cursor() as cursor:
        # Hard backend profile completeness validation check
        cursor.execute("SELECT cv_path FROM users WHERE id = %s", (session["user_id"],))
        user_profile = cursor.fetchone()
        if not user_profile or not user_profile.get("cv_path"):
            return jsonify({"success": False, "message": "Your profile is incomplete. You must build a professional CV first before applying!"})

        # Check if already applied
        cursor.execute("SELECT id FROM applications WHERE user_id = %s AND job_id = %s", (session["user_id"], job_id))
        existing = cursor.fetchone()
        if existing:
            return jsonify({"success": False, "message": "You have already applied for this opportunity!"})
            
        # Parse screening answers from request payload
        import json
        data = request.get_json() or {}
        answers = data.get("answers", [])
        answers_json = json.dumps(answers) if answers else None
            
        # Record application with answers
        cursor.execute("INSERT INTO applications (user_id, job_id, answers) VALUES (%s, %s, %s)", (session["user_id"], job_id, answers_json))
        
        # Log application
        print(f"[Application Log] Candidate {session['user_name']} (ID: {session['user_id']}) applied to job ID {job_id}")
        try:
            from my_first_flask.utils.logger import log_activity
            log_activity("Apply Opportunity", f"Candidate {session['user_name']} (ID: {session['user_id']}) applied to job ID {job_id}")
        except Exception as log_err:
            print(f"Failed to write apply log: {log_err}")
        
    return jsonify({"success": True, "message": "Your application has been successfully submitted!"})



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


# ─── CV BUILDER / UPLOADER ──────────────────────────────────────────────────

def generate_cv_html(data):
    import re
    
    def format_bold(text):
        return re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

    full_name = data.get("full_name", "")
    email = data.get("email", "")
    portfolio = data.get("portfolio", "")
    github = data.get("github", "")
    linkedin = data.get("linkedin", "")
    
    # Header links
    links_list = []
    if email:
        links_list.append(f'<a href="mailto:{email}">Email</a>')
    if portfolio:
        port_url = portfolio if (portfolio.startswith("http://") or portfolio.startswith("https://")) else f"https://{portfolio}"
        links_list.append(f'<a href="{port_url}" target="_blank">Portfolio</a>')
    if github:
        git_url = github if (github.startswith("http://") or github.startswith("https://")) else f"https://{github}"
        links_list.append(f'<a href="{git_url}" target="_blank">Github</a>')
    if linkedin:
        li_url = linkedin if (linkedin.startswith("http://") or linkedin.startswith("https://")) else f"https://{linkedin}"
        links_list.append(f'<a href="{li_url}" target="_blank">Linkedin</a>')
        
    links_html = " | ".join(links_list)
    
    # Education HTML
    edu_html = ""
    if data.get("education"):
        edu_html += '<div class="section-title">Education</div>'
        for edu in data["education"]:
            details_str = f'<div class="entry-details">{edu["details"]}</div>' if edu.get("details") else ''
            edu_html += f"""
            <div class="entry">
                <div class="entry-header">
                    <span class="entry-title">{edu["degree"]}</span>
                </div>
                <div class="entry-subtitle">{edu["school"]}</div>
                {details_str}
            </div>
            """
            
    # Work Experience HTML
    exp_html = ""
    if data.get("experience"):
        exp_html += '<div class="section-title">Work Experience</div>'
        for exp in data["experience"]:
            desc_html = ""
            if exp.get("description"):
                bullets = exp["description"].split("\n")
                bullets_li = "".join([f"<li>{format_bold(b.strip().lstrip('-*').strip())}</li>" for b in bullets if b.strip()])
                if bullets_li:
                    desc_html = f'<ul class="bullets">{bullets_li}</ul>'
                    
            dates_str = f'<span class="entry-tag">{exp["dates"]}</span>' if exp.get("dates") else ''
            exp_html += f"""
            <div class="entry">
                <div class="entry-header">
                    <span class="entry-title">{exp["title"]}</span>
                    {dates_str}
                </div>
                <div class="entry-subtitle">{exp["company"]}</div>
                {desc_html}
            </div>
            """
            
    # Projects HTML
    proj_html = ""
    if data.get("projects"):
        proj_html += '<div class="section-title">Projects</div>'
        for proj in data["projects"]:
            desc_html = ""
            if proj.get("description"):
                bullets = proj["description"].split("\n")
                bullets_li = "".join([f"<li>{format_bold(b.strip().lstrip('-*').strip())}</li>" for b in bullets if b.strip()])
                if bullets_li:
                    desc_html = f'<ul class="bullets">{bullets_li}</ul>'
            
            link_html = ""
            if proj.get("link"):
                p_url = proj["link"] if (proj["link"].startswith("http://") or proj["link"].startswith("https://")) else f"https://{proj['link']}"
                link_html = f'<div class="project-link"><a href="{p_url}" target="_blank">Github</a></div>'
                
            tag_str = f'<span class="entry-tag">({proj["tag"]})</span>' if proj.get("tag") else ''
            proj_html += f"""
            <div class="entry">
                <div class="entry-header">
                    <span class="entry-title">"{proj["title"]}"</span>
                    {tag_str}
                </div>
                {desc_html}
                {link_html}
            </div>
            """
            
    # Technical Skills HTML
    skills_html = ""
    if data.get("skills"):
        skills_html += '<div class="section-title">Skills</div>'
        skills_html += '<ul class="skills-list">'
        for sk in data["skills"]:
            skills_html += f'<li><strong>{sk["category"]}</strong>: {sk["list"]}</li>'
        skills_html += '</ul>'
        
    # Certifications HTML
    certs_html = ""
    if data.get("certifications"):
        certs_html += '<div class="section-title">Certifications</div>'
        certs_html += '<ul class="certifications-list">'
        for cert in data["certifications"]:
            certs_html += f'<li>{cert}</li>'
        certs_html += '</ul>'
        
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{full_name} - CV</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #111827;
            line-height: 1.5;
            margin: 40px auto;
            max-width: 800px;
            padding: 0 20px;
            background: #fff;
        }}
        
        .header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        
        .header h1 {{
            font-size: 26px;
            margin: 0 0 8px 0;
            color: #000;
            font-weight: 700;
        }}
        
        .links {{
            font-size: 14px;
            color: #2563eb;
            margin: 0;
        }}
        
        .links a {{
            color: #2563eb;
            text-decoration: underline;
        }}
        
        .links span {{
            color: #374151;
            margin: 0 6px;
        }}
        
        .section-title {{
            font-size: 16px;
            color: #1e3a8a;
            border-bottom: 1.5px solid #cbd5e1;
            padding-bottom: 3px;
            margin-top: 22px;
            margin-bottom: 10px;
            font-weight: 700;
            text-transform: capitalize;
        }}
        
        .entry {{
            margin-bottom: 12px;
        }}
        
        .entry-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
        }}
        
        .entry-title {{
            font-size: 14px;
            color: #000;
            font-weight: 700;
        }}
        
        .entry-tag {{
            font-size: 13px;
            color: #374151;
            font-weight: normal;
        }}
        
        .entry-subtitle {{
            font-size: 13.5px;
            color: #374151;
            margin: 1px 0;
        }}
        
        .entry-details {{
            font-size: 13px;
            color: #4b5563;
            margin: 1px 0;
        }}
        
        .bullets {{
            margin: 3px 0 0 0;
            padding-left: 20px;
            font-size: 13px;
            color: #111827;
        }}
        
        .bullets li {{
            margin-bottom: 3px;
        }}
        
        .bullets li strong {{
            color: #000;
        }}
        
        .project-link {{
            font-size: 13px;
            margin-top: 2px;
            padding-left: 20px;
        }}
        
        .project-link a {{
            color: #2563eb;
            text-decoration: underline;
        }}
        
        .skills-list {{
            list-style: none;
            padding: 0;
            margin: 0;
            font-size: 13.5px;
        }}
        
        .skills-list li {{
            margin-bottom: 4px;
        }}
        
        .certifications-list {{
            padding-left: 20px;
            margin: 0;
            font-size: 13.5px;
        }}
        
        .certifications-list li {{
            margin-bottom: 3px;
            font-weight: 700;
            color: #111827;
        }}
        
        @media print {{
            body {{
                margin: 20px;
                max-width: 100%;
                font-size: 12px;
            }}
            .section-title {{
                margin-top: 15px;
                margin-bottom: 8px;
            }}
            .entry {{
                margin-bottom: 8px;
            }}
            .print-bar {{
                display: none !important;
            }}
        }}
        
        .print-bar {{
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
        }}
        
        .print-btn {{
            background: #2456ff;
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(36, 86, 255, 0.3);
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
            text-decoration: none;
        }}
        
        .print-btn:hover {{
            background: #1848d8;
            transform: translateY(-1px);
        }}
    </style>
</head>
<body>
    <div class="print-bar">
        <button onclick="window.print()" class="print-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 6px; display: inline-block; vertical-align: middle;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download PDF
        </button>
    </div>

    <div class="header">
        <h1>{full_name}</h1>
        <div class="links">{links_html}</div>
    </div>
    
    {edu_html}
    {exp_html}
    {proj_html}
    {skills_html}
    {certs_html}
    
    <script>
        if (window.location.search.includes('print=true')) {{
            window.onload = function() {{
                window.print();
            }}
        }}
    </script>
</body>
</html>"""
    return html_template


@app.route("/dashboard/cv", methods=["GET"])
@login_required
def dashboard_cv():
    if session.get("account_type") != "individual":
        flash("Only individuals can access the CV Builder.", "error")
        return redirect(url_for("dashboard"))
        
    import json
    
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT cv_path, cv_data FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
        
    cv_data_str = user["cv_data"] if user and user["cv_data"] else "{}"
    
    try:
        cv_data = json.loads(cv_data_str)
    except Exception:
        cv_data = {}
        
    return render_template(
        "dashboard_cv.html", 
        user_cv_path=user["cv_path"] if user else None,
        cv_data=cv_data,
        cv_data_raw=cv_data_str
    )


@app.route("/cv/view/<int:user_id>", methods=["GET"])
def view_cv(user_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT cv_path, cv_data, account_type FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
    if not user or user["account_type"] != "individual":
        flash("CV not found.", "error")
        return redirect(url_for("home"))
        
    cv_path = user.get("cv_path")
    cv_data_str = user.get("cv_data")
    
    # If they uploaded a static file (PDF/PNG/etc.)
    if cv_path and not cv_path.lower().endswith(".html"):
        full_path = os.path.join(BASE_DIR, cv_path.lstrip("/"))
        if os.path.exists(full_path):
            # If download or print parameter is requested, serve as a downloadable attachment
            if request.args.get("download") == "true" or request.args.get("print") == "true":
                from flask import send_file
                filename = os.path.basename(full_path)
                return send_file(full_path, as_attachment=True, download_name=filename)
            return redirect(cv_path)
            
    # Try dynamic HTML generation on the fly if CV JSON data is available
    if cv_data_str:
        import json
        try:
            cv_data = json.loads(cv_data_str)
            if cv_data:
                html_content = generate_cv_html(cv_data)
                return html_content
        except Exception:
            pass
            
    # Fallback to static HTML file if exists on disk
    if cv_path:
        full_path = os.path.join(BASE_DIR, cv_path.lstrip("/"))
        if os.path.exists(full_path):
            if request.args.get("download") == "true":
                from flask import send_file
                filename = os.path.basename(full_path)
                return send_file(full_path, as_attachment=True, download_name=filename)
            return redirect(cv_path)
            
    flash("This candidate does not have a valid active CV on the server.", "error")
    return redirect(url_for("home"))


@app.route("/dashboard/cv/build", methods=["POST"])
@login_required
def dashboard_cv_build():
    if session.get("account_type") != "individual":
        flash("Only individuals can build a CV.", "error")
        return redirect(url_for("dashboard"))
        
    import json
    
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    portfolio = request.form.get("portfolio", "").strip()
    github = request.form.get("github", "").strip()
    linkedin = request.form.get("linkedin", "").strip()
    
    # Process Education lists
    edu_degrees = request.form.getlist("edu_degree[]")
    edu_schools = request.form.getlist("edu_school[]")
    edu_details = request.form.getlist("edu_details[]")
    education = []
    for i in range(len(edu_degrees)):
        if edu_degrees[i].strip() or edu_schools[i].strip():
            education.append({
                "degree": edu_degrees[i].strip(),
                "school": edu_schools[i].strip(),
                "details": edu_details[i].strip()
            })
            
    # Process Experience lists
    exp_titles = request.form.getlist("exp_title[]")
    exp_companies = request.form.getlist("exp_company[]")
    exp_dates = request.form.getlist("exp_dates[]")
    exp_descriptions = request.form.getlist("exp_description[]")
    experience = []
    for i in range(len(exp_titles)):
        if exp_titles[i].strip() or exp_companies[i].strip():
            experience.append({
                "title": exp_titles[i].strip(),
                "company": exp_companies[i].strip(),
                "dates": exp_dates[i].strip(),
                "description": exp_descriptions[i].strip()
            })
            
    # Process Projects lists
    proj_titles = request.form.getlist("proj_title[]")
    proj_tags = request.form.getlist("proj_tag[]")
    proj_links = request.form.getlist("proj_link[]")
    proj_descriptions = request.form.getlist("proj_description[]")
    projects = []
    for i in range(len(proj_titles)):
        if proj_titles[i].strip():
            projects.append({
                "title": proj_titles[i].strip(),
                "tag": proj_tags[i].strip(),
                "link": proj_links[i].strip(),
                "description": proj_descriptions[i].strip()
            })
            
    # Process Skills lists
    skill_categories = request.form.getlist("skill_category[]")
    skill_lists = request.form.getlist("skill_list[]")
    skills = []
    for i in range(len(skill_categories)):
        if skill_categories[i].strip() or skill_lists[i].strip():
            skills.append({
                "category": skill_categories[i].strip(),
                "list": skill_lists[i].strip()
            })
            
    # Process Certifications
    cert_names = request.form.getlist("cert_name[]")
    certifications = [c.strip() for c in cert_names if c.strip()]
    
    cv_data_dict = {
        "full_name": full_name,
        "email": email,
        "portfolio": portfolio,
        "github": github,
        "linkedin": linkedin,
        "education": education,
        "experience": experience,
        "projects": projects,
        "skills": skills,
        "certifications": certifications
    }
    
    cv_data_json = json.dumps(cv_data_dict)
    
    # Now generate the HTML template
    html_content = generate_cv_html(cv_data_dict)
    
    static_uploads_dir = os.path.join(BASE_DIR, "static", "uploads")
    os.makedirs(static_uploads_dir, exist_ok=True)
    
    cv_filename = f"cv_{session['user_id']}_{int(time.time())}.html"
    cv_filepath = os.path.join(static_uploads_dir, cv_filename)
    
    with open(cv_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    cv_path = f"/static/uploads/{cv_filename}"
    
    # Save to Database
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE users SET cv_path = %s, cv_data = %s WHERE id = %s",
            (cv_path, cv_data_json, session["user_id"])
        )
        
    flash("CV successfully built and set active!", "success")
    return redirect(url_for("dashboard_cv"))


@app.route("/dashboard/cv/upload", methods=["POST"])
@login_required
def dashboard_cv_upload():
    if session.get("account_type") != "individual":
        flash("Only individuals can upload a CV.", "error")
        return redirect(url_for("dashboard"))
        
    cv_file = request.files.get("cv_file")
    allowed_extensions = {"pdf", "doc", "docx", "png", "jpg", "jpeg"}
    
    if cv_file and cv_file.filename:
        ext = cv_file.filename.rsplit(".", 1)[-1].lower()
        if ext in allowed_extensions:
            static_uploads_dir = os.path.join(BASE_DIR, "static", "uploads")
            os.makedirs(static_uploads_dir, exist_ok=True)
            
            filename = f"cv_uploaded_{session['user_id']}_{int(time.time())}.{ext}"
            filepath = os.path.join(static_uploads_dir, filename)
            cv_file.save(filepath)
            
            cv_path = f"/static/uploads/{filename}"
            
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET cv_path = %s WHERE id = %s",
                    (cv_path, session["user_id"])
                )
                
            flash("CV file uploaded successfully and set active!", "success")
        else:
            flash("Invalid file type. Supported formats: PDF, DOC, DOCX, PNG, JPG, JPEG.", "error")
    else:
        flash("No file selected.", "error")
        
    return redirect(url_for("dashboard_cv"))


@app.route("/dashboard/events")
@login_required
def dashboard_events():
    return render_template("dashboard_events.html")


@app.route("/dashboard/post-opportunity", methods=["GET", "POST"])
@login_required
def dashboard_post_opportunity():
    if session.get("account_type") != "company":
        flash("Only company accounts can post opportunities.", "error")
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        opportunity_type = request.form.get("opportunity_type", "job").strip()
        
        city = request.form.get("city", "").strip()
        location_type = request.form.get("location", "Onsite").strip()
        location = f"{city} ({location_type})" if city else location_type
        
        min_salary = request.form.get("min_salary", "").strip()
        max_salary = request.form.get("max_salary", "").strip()
        salary_cycle = request.form.get("salary_cycle", "Monthly").strip()
        
        salary = f"Rs. {min_salary}"
        if max_salary:
            salary += f" - Rs. {max_salary}"
        salary += f" {salary_cycle}"
        
        min_exp = request.form.get("min_experience", "").strip()
        max_exp = request.form.get("max_experience", "").strip()
        
        if min_exp:
            experience_level = f"{min_exp}"
            if max_exp:
                experience_level += f" - {max_exp}"
            experience_level += " Years"
        else:
            experience_level = request.form.get("experience_level", "Entry").strip()
            
        skills_required = request.form.get("skills_required", "").strip()
        apply_link = request.form.get("apply_link", "").strip()
        description = request.form.get("description", "").strip()
        
        # Serialize optional screening questions to JSON
        import json
        questions_list = [q.strip() for q in request.form.getlist("questions[]") if q.strip()]
        questions_json = json.dumps(questions_list) if questions_list else None
        
        if not title or not description:
            flash("Opportunity title and detailed description are required.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, company_name FROM companies WHERE user_id = %s", (session["user_id"],))
            company = cursor.fetchone()
            
        if not company:
            flash("Please complete your company profile before posting an opportunity.", "error")
            return redirect(url_for("profile"))
            
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO jobs (company_id, title, opportunity_type, location, salary, experience_level, skills_required, description, apply_link, questions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                company["id"],
                title,
                opportunity_type,
                location,
                salary,
                experience_level,
                skills_required or None,
                description,
                apply_link or None,
                questions_json
            ))
            
        # Log job posting event
        print(f"[JOB LOG] User {session['user_id']} ({company['company_name']}) posted a new {opportunity_type}: '{title}' at {location}")
        try:
            from my_first_flask.utils.logger import log_activity
            log_activity("Post Opportunity", f"Company '{company['company_name']}' (ID: {company['id']}) posted a new {opportunity_type}: '{title}' at {location}")
        except Exception as log_err:
            print(f"Failed to write post job log: {log_err}")
        
        flash("Opportunity successfully published!", "success")
        return redirect(url_for("dashboard"))
        
    return render_template("dashboard_post_opportunity.html")




# ─── CONTACT / SEND EMAIL ─────────────────────────────────────────────────────

@app.route("/send-email", methods=["POST"])
def send_email():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "No data received."}), 400

    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    message_body = data.get("message", "").strip()

    if not name or not email or not message_body:
        return jsonify({"success": False, "message": "All fields are required."}), 400

    try:
        msg = Message(
            subject=f"New Contact Message from {name} — Talent Khoj",
            sender=config.MAIL_USERNAME,
            recipients=[config.MAIL_USERNAME],
            reply_to=email,
            body=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message_body}"
        )
        mail.send(msg)
        try:
            from my_first_flask.utils.logger import log_activity
            log_activity("Contact Email", f"Sender '{name}' ({email}) successfully sent a contact message: '{message_body[:60]}...'")
        except Exception as log_err:
            print(f"Failed to log contact email activity: {log_err}")
            
        return jsonify({"success": True, "message": "Email sent successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to send email: {str(e)}"}), 500


# ── Google OAuth ──────────────────────────────────────────────────────────────

@app.route("/login/google")
def google_login():
    redirect_uri = "http://127.0.0.1:5000/login/google/callback"
    print(f"Using hardcoded redirect URI: {redirect_uri}")
    return google.authorize_redirect(redirect_uri)


@app.route("/login/google/callback")
def google_callback():
    try:
        token = google.authorize_access_token()
    except Exception:
        # State mismatch — redirect back to Google login to retry
        return redirect(url_for("google_login"))

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


# ─── ADMIN DASHBOARD ─────────────────────────────────────────────────────────

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    with conn.cursor() as cursor:
        # Total Users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_users = cursor.fetchone()["count"]

        # Pending Reports
        cursor.execute("SELECT COUNT(*) as count FROM reports WHERE status = 'Pending'")
        pending_reports = cursor.fetchone()["count"]

        # Pending Verifications (unverified companies)
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE account_type = 'company' AND verified = 0")
        pending_verifications = cursor.fetchone()["count"]

        # Active Projects (Jobs)
        cursor.execute("SELECT COUNT(*) as count FROM jobs")
        active_projects = cursor.fetchone()["count"]

        # Total Applications
        cursor.execute("SELECT COUNT(*) as count FROM applications")
        total_applications = cursor.fetchone()["count"]

        # Total Companies
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE account_type = 'company'")
        total_companies = cursor.fetchone()["count"]

        # Growth: new users in last 30 days vs previous 30 days
        cursor.execute("""
            SELECT
                SUM(CASE WHEN created_at >= NOW() - INTERVAL 30 DAY THEN 1 ELSE 0 END) as current_period,
                SUM(CASE WHEN created_at >= NOW() - INTERVAL 60 DAY
                          AND created_at < NOW() - INTERVAL 30 DAY THEN 1 ELSE 0 END) as prev_period
            FROM users
        """)
        row = cursor.fetchone()
        cur_u = row["current_period"] or 0
        prev_u = row["prev_period"] or 1
        user_growth = round(((cur_u - prev_u) / prev_u) * 100) if prev_u else 0

        # Growth: new jobs in last 30 days vs previous 30 days
        cursor.execute("""
            SELECT
                SUM(CASE WHEN created_at >= NOW() - INTERVAL 30 DAY THEN 1 ELSE 0 END) as current_period,
                SUM(CASE WHEN created_at >= NOW() - INTERVAL 60 DAY
                          AND created_at < NOW() - INTERVAL 30 DAY THEN 1 ELSE 0 END) as prev_period
            FROM jobs
        """)
        row = cursor.fetchone()
        cur_j = row["current_period"] or 0
        prev_j = row["prev_period"] or 1
        job_growth = round(((cur_j - prev_j) / prev_j) * 100) if prev_j else 0

        # Recent Reports
        cursor.execute("""
            SELECT r.id, r.type, r.content, r.status, r.created_at, u.full_name as user
            FROM reports r
            LEFT JOIN users u ON r.user_id = u.id
            ORDER BY r.created_at DESC
            LIMIT 5
        """)
        db_reports = cursor.fetchall()
        recent_reports = []
        for r in db_reports:
            recent_reports.append({
                "id": r["id"],
                "type": r["type"],
                "content": r["content"],
                "user": r["user"] or "Anonymous",
                "status": r["status"],
                "date": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
            })
            
        # Recent Activities (Users and Jobs)
        cursor.execute("SELECT full_name, created_at FROM users ORDER BY created_at DESC LIMIT 4")
        recent_users = cursor.fetchall()
        
        cursor.execute("""
            SELECT j.title, c.company_name, j.created_at 
            FROM jobs j 
            JOIN companies c ON j.company_id = c.id 
            ORDER BY j.created_at DESC 
            LIMIT 4
        """)
        recent_jobs = cursor.fetchall()
        
        recent_activities = []
        for u in recent_users:
            recent_activities.append({
                "user": u["full_name"],
                "action": "registered a new account",
                "details": "User registered",
                "time_ago": u["created_at"].strftime("%b %d, %H:%M") if u["created_at"] else "",
                "color": "primary",
                "icon": "user-plus"
            })
        for j in recent_jobs:
            recent_activities.append({
                "user": j["company_name"],
                "action": f"posted a new opportunity: {j['title']}",
                "details": "Active listing",
                "time_ago": j["created_at"].strftime("%b %d, %H:%M") if j["created_at"] else "",
                "color": "success",
                "icon": "briefcase"
            })
            
        recent_activities = sorted(recent_activities, key=lambda x: x["time_ago"], reverse=True)[:6]

        # Recent Registrations (last 6 signups)
        cursor.execute("""
            SELECT id, full_name, email, account_type, verified, created_at
            FROM users ORDER BY created_at DESC LIMIT 6
        """)
        recent_reg_rows = cursor.fetchall()
        recent_registrations = [{
            "id": r["id"],
            "full_name": r["full_name"],
            "email": r["email"],
            "account_type": r["account_type"],
            "verified": r["verified"],
            "date": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
        } for r in recent_reg_rows]

    class CurrentUserMock:
        username = session.get("user_name", "Admin")

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        pending_reports=pending_reports,
        pending_verifications=pending_verifications,
        active_projects=active_projects,
        total_applications=total_applications,
        total_companies=total_companies,
        user_growth=user_growth,
        job_growth=job_growth,
        recent_reports=recent_reports,
        recent_activities=recent_activities,
        recent_registrations=recent_registrations,
        current_user=CurrentUserMock()
    )


# ─── ADMIN CHART APIS (Commit 2) ─────────────────────────────────────────────

@app.route("/admin/api/stats/registrations")
@admin_required
def admin_stats_registrations():
    """Return daily new-user counts for the last 30 days."""
    from datetime import date, timedelta
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT DATE(created_at) as day, COUNT(*) as count
            FROM users
            WHERE created_at >= NOW() - INTERVAL 30 DAY
            GROUP BY DATE(created_at)
            ORDER BY day ASC
        """)
        rows = cursor.fetchall()

    today = date.today()
    data_map = {str(r["day"]): r["count"] for r in rows}
    labels, counts = [], []
    for i in range(30):
        d = today - timedelta(days=29 - i)
        labels.append(d.strftime("%b %d"))
        counts.append(data_map.get(str(d), 0))
    return jsonify({"labels": labels, "counts": counts})


@app.route("/admin/api/stats/roles")
@admin_required
def admin_stats_roles():
    """Return count of users by account_type for the donut chart."""
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT account_type, COUNT(*) as count FROM users GROUP BY account_type")
        rows = cursor.fetchall()
    role_map = {r["account_type"]: r["count"] for r in rows}
    return jsonify({
        "individual": role_map.get("individual", 0),
        "company": role_map.get("company", 0),
        "admin": role_map.get("admin", 0)
    })



@app.route("/admin/reports")
@admin_required
def admin_reports():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM reports")
        total_reports = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM reports WHERE status = 'Pending'")
        pending_reports = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM reports WHERE status = 'Resolved'")
        resolved_reports = cursor.fetchone()["count"]
        
        cursor.execute("""
            SELECT r.id, r.type, r.content, r.status, r.created_at, u.full_name as user 
            FROM reports r 
            LEFT JOIN users u ON r.user_id = u.id 
            ORDER BY r.created_at DESC
        """)
        db_reports = cursor.fetchall()
        reports_list = []
        for r in db_reports:
            reports_list.append({
                "id": r["id"],
                "type": r["type"],
                "content": r["content"],
                "user": r["user"] or "Anonymous",
                "status": r["status"],
                "date": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
            })
            
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_report.html",
        total_reports=total_reports,
        pending_reports=pending_reports,
        resolved_reports=resolved_reports,
        reports=reports_list,
        current_user=CurrentUserMock()
    )


@app.route("/admin/report/<int:report_id>")
@admin_required
def view_report(report_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT r.id, r.type, r.content, r.status, r.created_at, u.id as user_id, u.full_name as user_name, u.email as user_email
            FROM reports r 
            LEFT JOIN users u ON r.user_id = u.id 
            WHERE r.id = %s
        """, (report_id,))
        report = cursor.fetchone()
        
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("admin_reports"))
        
    report_data = {
        "id": report["id"],
        "type": report["type"],
        "content": report["content"],
        "status": report["status"],
        "user_id": report["user_id"],
        "user_name": report["user_name"] or "Anonymous",
        "user_email": report["user_email"] or "N/A",
        "date": report["created_at"].strftime("%b %d, %Y %H:%M") if report["created_at"] else ""
    }
    
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_view_report.html",
        report=report_data,
        current_user=CurrentUserMock()
    )


@app.route("/admin/report/resolve", methods=["POST"])
@admin_required
def resolve_reports():
    data = request.get_json() or {}
    report_ids = data.get("ids", [])
    if not report_ids:
        return jsonify({"success": False, "message": "No reports selected."}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        format_strings = ','.join(['%s'] * len(report_ids))
        cursor.execute(f"UPDATE reports SET status = 'Resolved' WHERE id IN ({format_strings})", tuple(report_ids))
        
    return jsonify({"success": True, "message": "Selected reports marked as resolved."})


@app.route("/admin/report/delete", methods=["POST"])
@admin_required
def delete_reports():
    data = request.get_json() or {}
    report_ids = data.get("ids", [])
    if not report_ids:
        return jsonify({"success": False, "message": "No reports selected."}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        format_strings = ','.join(['%s'] * len(report_ids))
        cursor.execute(f"DELETE FROM reports WHERE id IN ({format_strings})", tuple(report_ids))
        
    return jsonify({"success": True, "message": "Selected reports deleted successfully."})


@app.route("/admin/users")
@admin_required
def admin_users():
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "").strip()
    
    conn = get_db()
    query = "SELECT id, full_name, email, account_type, verified, created_at FROM users"
    params = []
    
    conditions = []
    if search:
        conditions.append("(full_name LIKE %s OR email LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if role_filter:
        conditions.append("account_type = %s")
        params.append(role_filter)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY created_at DESC"
    
    with conn.cursor() as cursor:
        cursor.execute(query, tuple(params))
        db_users = cursor.fetchall()
        
    users_list = []
    for u in db_users:
        users_list.append({
            "id": u["id"],
            "full_name": u["full_name"],
            "email": u["email"],
            "account_type": u["account_type"],
            "verified": u["verified"],
            "date": u["created_at"].strftime("%b %d, %Y") if u["created_at"] else ""
        })
        
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_users.html",
        users=users_list,
        search=search,
        selected_role=role_filter,
        current_user=CurrentUserMock()
    )


@app.route("/admin/user/toggle-verify/<int:user_id>", methods=["POST"])
@admin_required
def toggle_user_verify(user_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT verified FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404
            
        new_val = 0 if user["verified"] else 1
        cursor.execute("UPDATE users SET verified = %s WHERE id = %s", (new_val, user_id))
        
    status_str = "verified" if new_val else "unverified"
    return jsonify({"success": True, "message": f"User status set to {status_str}."})


@app.route("/admin/user/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"success": False, "message": "You cannot delete yourself!"}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        
    return jsonify({"success": True, "message": "User account permanently deleted."})


@app.route("/admin/user/change-role/<int:user_id>", methods=["POST"])
@admin_required
def change_user_role(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"success": False, "message": "You cannot change your own role!"}), 400

    data = request.get_json() or {}
    new_role = data.get("role", "").strip().lower()

    allowed_roles = ("individual", "company", "admin")
    if new_role not in allowed_roles:
        return jsonify({"success": False, "message": f"Invalid role. Choose from: {', '.join(allowed_roles)}."}), 400

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, account_type FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404

        cursor.execute("UPDATE users SET account_type = %s WHERE id = %s", (new_role, user_id))

    
    return jsonify({"success": True, "message": f"User role updated to '{new_role.capitalize()}' successfully."})


# ─── BAN / UNBAN USERS (Commit 3) ────────────────────────────────────────────

@app.route("/admin/user/ban/<int:user_id>", methods=["POST"])
@admin_required
def ban_user(user_id):
    if user_id == session.get("user_id"):
        return jsonify({"success": False, "message": "You cannot ban yourself!"}), 400

    data = request.get_json() or {}
    reason = data.get("reason", "").strip() or "Violation of platform terms."

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, full_name FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404
        cursor.execute(
            "UPDATE users SET is_banned = 1, ban_reason = %s WHERE id = %s",
            (reason, user_id)
        )
    
    return jsonify({"success": True, "message": f"User '{user['full_name']}' has been suspended."})


@app.route("/admin/user/unban/<int:user_id>", methods=["POST"])
@admin_required
def unban_user(user_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, full_name FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404
        cursor.execute(
            "UPDATE users SET is_banned = 0, ban_reason = NULL WHERE id = %s",
            (user_id,)
        )
    
    return jsonify({"success": True, "message": f"User '{user['full_name']}' has been reinstated."})



@app.route("/admin/verification")
@admin_required
def admin_verification():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.full_name as company_name, u.email, c.address, c.pan_number, u.created_at
            FROM users u
            JOIN companies c ON u.id = c.user_id
            WHERE u.account_type = 'company' AND u.verified = 0
            ORDER BY u.created_at DESC
        """)
        companies = cursor.fetchall()
        
    companies_list = []
    for c in companies:
        companies_list.append({
            "id": c["id"],
            "company_name": c["company_name"],
            "email": c["email"],
            "address": c["address"] or "N/A",
            "pan_number": c["pan_number"] or "N/A",
            "date": c["created_at"].strftime("%b %d, %Y") if c["created_at"] else ""
        })
        
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_verification.html",
        companies=companies_list,
        current_user=CurrentUserMock()
    )


@app.route("/admin/projects")
@admin_required
def admin_projects():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT j.id, j.title, j.opportunity_type, j.location, j.salary, j.created_at, c.company_name
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            ORDER BY j.created_at DESC
        """)
        jobs = cursor.fetchall()
        
    projects_list = []
    for j in jobs:
        projects_list.append({
            "id": j["id"],
            "title": j["title"],
            "type": j["opportunity_type"],
            "location": j["location"] or "Remote",
            "salary": j["salary"] or "N/A",
            "company": j["company_name"],
            "date": j["created_at"].strftime("%b %d, %Y") if j["created_at"] else ""
        })
        
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_projects.html",
        projects=projects_list,
        current_user=CurrentUserMock()
    )


@app.route("/admin/project/delete/<int:job_id>", methods=["POST"])
@admin_required
def delete_project(job_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        
    return jsonify({"success": True, "message": "Opportunity deleted successfully."})


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    errors = []
    success = None
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "change_password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")
            
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute("SELECT password_hash FROM users WHERE id = %s", (session["user_id"],))
                u = cursor.fetchone()
                
            if not u or not check_password_hash(u["password_hash"], current_pw):
                errors.append("Current password is incorrect.")
            if len(new_pw) < 8:
                errors.append("New password must be at least 8 characters.")
            if new_pw != confirm_pw:
                errors.append("Confirm password does not match.")
                
            if not errors:
                new_hash = generate_password_hash(new_pw)
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, session["user_id"]))
                success = "Password updated successfully."
                
        elif action == "create_admin":
            admin_name = request.form.get("admin_name", "").strip()
            admin_email = request.form.get("admin_email", "").strip().lower()
            admin_password = request.form.get("admin_password", "")
            
            if not admin_name or not admin_email or not admin_password:
                errors.append("All fields are required to create a new admin.")
            else:
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
                    if cursor.fetchone():
                        errors.append("Email is already registered.")
                        
                if not errors:
                    pw_hash = generate_password_hash(admin_password)
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO users (full_name, email, password_hash, account_type, verified, email_verified) "
                            "VALUES (%s, %s, %s, 'admin', 1, 1)",
                            (admin_name, admin_email, pw_hash)
                        )
                    success = f"New administrator account for {admin_name} created successfully!"
                    
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_settings.html",
        errors=errors,
        success_message=success,
        current_user=CurrentUserMock()
    )


# ─── ANNOUNCEMENTS ────────────────────────────────────────────────────────────

@app.route("/admin/announcement/send", methods=["POST"])
@admin_required
def send_announcement():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    message = data.get("message", "").strip()
    target = data.get("target", "all")

    if not title or not message:
        return jsonify({"success": False, "message": "Title and message are required."}), 400
    if target not in ("all", "verified", "new"):
        target = "all"

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO announcements (title, message, target, created_by) VALUES (%s, %s, %s, %s)",
            (title, message, target, session["user_id"])
        )

    return jsonify({"success": True, "message": "Announcement sent successfully!"})


@app.route("/api/announcements")
@login_required
def get_announcements():
    """Return unread announcements for the logged-in user."""
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT a.id, a.title, a.message, a.created_at
            FROM announcements a
            WHERE a.id NOT IN (
                SELECT announcement_id FROM announcement_reads WHERE user_id = %s
            )
            ORDER BY a.created_at DESC
            LIMIT 10
        """, (user_id,))
        rows = cursor.fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "title": r["title"],
            "message": r["message"],
            "time": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
        })

    return jsonify({"announcements": result, "count": len(result)})


@app.route("/api/announcements/read", methods=["POST"])
@login_required
def mark_announcement_read():
    """Mark one or all announcements as read."""
    data = request.get_json() or {}
    ann_id = data.get("id")  # None means mark all
    user_id = session["user_id"]
    conn = get_db()

    if ann_id:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO announcement_reads (user_id, announcement_id) VALUES (%s, %s)",
                (user_id, ann_id)
            )
    else:
        # Mark all unread as read
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM announcements WHERE id NOT IN (SELECT announcement_id FROM announcement_reads WHERE user_id = %s)", (user_id,))
            ids = [row["id"] for row in cursor.fetchall()]
        for aid in ids:
            with conn.cursor() as cursor:
                cursor.execute("INSERT IGNORE INTO announcement_reads (user_id, announcement_id) VALUES (%s, %s)", (user_id, aid))

    return jsonify({"success": True})




if __name__ == "__main__":
    app.run(debug=True)
