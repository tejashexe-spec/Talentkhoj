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
app.config['MAIL_DEFAULT_SENDER'] = config.MAIL_DEFAULT_SENDER
mail = Mail(app)
EmailService.mail = mail

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
EmailService._db = db


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


@app.route("/feed", methods=["GET"])
def get_feed():
    user_id = session.get("user_id", 0)
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1":
        conn = get_db()
        SQL_QUERY = """
            SELECT p.id, p.user_id, p.content, p.image_path, p.created_at,
                   u.full_name, u.avatar, u.account_type,
                   COUNT(DISTINCT r.id) AS like_count,
                   COUNT(DISTINCT c.id) AS comment_count,
                   EXISTS(SELECT 1 FROM reactions WHERE post_id = p.id AND user_id = %s) AS has_liked
            FROM posts p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN reactions r ON p.id = r.post_id AND r.reaction_type = 'like'
            LEFT JOIN comments c ON p.id = c.post_id
            GROUP BY p.id, u.id
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
        """
        with conn.cursor() as cursor:
            cursor.execute(SQL_QUERY, (user_id, per_page, offset))
            posts = cursor.fetchall()
            
        # Format datetimes
        for post in posts:
            if post.get("created_at"):
                post["created_at"] = post["created_at"].strftime("%Y-%m-%d %H:%M")

        return jsonify({"posts": posts})

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, full_name, avatar, bio, account_type FROM users WHERE id = %s", (user_id,))
        user_profile = cursor.fetchone()
        
        cursor.execute("SELECT id, full_name, avatar, bio, account_type FROM users WHERE id != %s ORDER BY RAND() LIMIT 3", (user_id,))
        suggestions = cursor.fetchall()
    return render_template("feed.html", user_profile=user_profile, suggestions=suggestions)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "gif", "webp"}


@app.route("/post/create", methods=["POST"])
@login_required
def create_post():
    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"success": False, "error": "Post content cannot be empty"}), 400

    image_path = None
    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        from werkzeug.utils import secure_filename
        import uuid
        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        
        # Ensure upload folder exists
        upload_folder = os.path.join(BASE_DIR, "static", "uploads", "posts")
        os.makedirs(upload_folder, exist_ok=True)
        
        file.save(os.path.join(upload_folder, unique_name))
        image_path = f"uploads/posts/{unique_name}"

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO posts (user_id, content, image_path) VALUES (%s, %s, %s)",
            (session["user_id"], content, image_path)
        )
    return jsonify({"success": True, "message": "Post published!"})


@app.route("/post/react", methods=["POST"])
@login_required
def toggle_reaction():
    data = request.get_json() or {}
    post_id = data.get("post_id")
    if not post_id:
        return jsonify({"success": False, "error": "Missing post_id"}), 400

    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM reactions WHERE user_id = %s AND post_id = %s", (user_id, post_id))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("DELETE FROM reactions WHERE user_id = %s AND post_id = %s", (user_id, post_id))
            action = "unliked"
        else:
            cursor.execute("INSERT INTO reactions (user_id, post_id, reaction_type) VALUES (%s, %s, 'like')", (user_id, post_id))
            action = "liked"
            
        cursor.execute("SELECT COUNT(*) as cnt FROM reactions WHERE post_id = %s", (post_id,))
        like_count = cursor.fetchone()["cnt"]

    return jsonify({"success": True, "action": action, "like_count": like_count})


@app.route("/post/<int:post_id>/comments", methods=["GET"])
def get_post_comments(post_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT c.*, u.full_name, u.avatar, u.account_type
            FROM comments c
            JOIN users u ON c.user_id = u.id
            WHERE c.post_id = %s
            ORDER BY c.created_at ASC
        """, (post_id,))
        flat_comments = cursor.fetchall()

    comment_map = {c["id"]: c for c in flat_comments}
    roots = []
    
    for c in flat_comments:
        if c.get("created_at"):
            c["created_at"] = c["created_at"].strftime("%Y-%m-%d %H:%M")
        c["replies"] = []
        parent_id = c["parent_comment_id"]
        if parent_id is None:
            roots.append(c)
        else:
            if parent_id in comment_map:
                if "replies" not in comment_map[parent_id]:
                    comment_map[parent_id]["replies"] = []
                comment_map[parent_id]["replies"].append(c)
                
    return jsonify({"comments": roots})


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def post_comment(post_id):
    data = request.get_json() or {}
    comment_text = data.get("comment_text", "").strip()
    parent_comment_id = data.get("parent_comment_id")

    if not comment_text:
        return jsonify({"success": False, "error": "Comment text cannot be empty"}), 400

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO comments (user_id, post_id, parent_comment_id, comment_text)
            VALUES (%s, %s, %s, %s)
        """, (session["user_id"], post_id, parent_comment_id, comment_text))
        
    return jsonify({"success": True, "message": "Comment posted successfully!"})





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

        # ── Headhunting Settings ─────────────────────────────────────────────
        elif action == "headhunting":
            active_status = request.form.get("active_status", "actively_looking").strip()
            headhunting_mode = 1 if request.form.get("headhunting_mode") == "on" else 0
            
            if active_status not in ("actively_looking", "open_to_offers", "not_looking"):
                active_status = "actively_looking"
                
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET active_status = %s, headhunting_mode = %s WHERE id = %s",
                    (active_status, headhunting_mode, session["user_id"])
                )
            name_message = "Headhunting settings updated successfully."

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
            "SELECT id, full_name, avatar, bio, location, skills, cv_path, active_status, headhunting_mode FROM users WHERE id = %s AND account_type = 'individual'",
            (user_id,)
        )
        user = cursor.fetchone()
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("home"))
        
    # Query reviews and rating stats
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT r.*, u.full_name as reviewer_name, u.avatar as reviewer_avatar, u.account_type as reviewer_type "
            "FROM reviews r JOIN users u ON r.reviewer_id = u.id "
            "WHERE r.reviewee_id = %s ORDER BY r.created_at DESC",
            (user_id,)
        )
        reviews = cursor.fetchall()
        
        cursor.execute(
            "SELECT AVG(rating) as avg_rating, COUNT(*) as review_count FROM reviews WHERE reviewee_id = %s",
            (user_id,)
        )
        stats = cursor.fetchone()
        avg_rating = round(stats["avg_rating"], 1) if stats["avg_rating"] else 0.0
        review_count = stats["review_count"]
        
        # Fetch accepted badges
        cursor.execute("""
            SELECT b.*, c.company_name, c.logo as company_logo
            FROM user_badges b
            JOIN companies c ON b.company_id = c.id
            WHERE b.user_id = %s AND b.status = 'accepted'
            ORDER BY b.end_date DESC, b.awarded_at DESC
        """, (user_id,))
        accepted_badges = cursor.fetchall()
        
    return render_template("user_profile.html", user=user, reviews=reviews, avg_rating=avg_rating, review_count=review_count, accepted_badges=accepted_badges)


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
        
    # Query reviews and rating stats
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT r.*, u.full_name as reviewer_name, u.avatar as reviewer_avatar, u.account_type as reviewer_type "
            "FROM reviews r JOIN users u ON r.reviewer_id = u.id "
            "WHERE r.reviewee_id = %s ORDER BY r.created_at DESC",
            (user_id,)
        )
        reviews = cursor.fetchall()
        
        cursor.execute(
            "SELECT AVG(rating) as avg_rating, COUNT(*) as review_count FROM reviews WHERE reviewee_id = %s",
            (user_id,)
        )
        stats = cursor.fetchone()
        avg_rating = round(stats["avg_rating"], 1) if stats["avg_rating"] else 0.0
        review_count = stats["review_count"]
        
        # Query FAQs
        cursor.execute(
            "SELECT * FROM company_faqs WHERE company_id = %s ORDER BY created_at ASC",
            (company["id"],)
        )
        faqs = cursor.fetchall()
        
    return render_template("company_profile.html", company=company, reviews=reviews, avg_rating=avg_rating, review_count=review_count, faqs=faqs)


@app.route("/company/edit", methods=["GET", "POST"])
@login_required
def edit_company_profile():
    if session.get("account_type") != "company":
        flash("Only company accounts can edit their profile.", "error")
        return redirect(url_for("home"))
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        flash("Company profile not found.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        address = request.form.get("address", "").strip()
        pan_number = request.form.get("pan_number", "").strip()
        industry = request.form.get("industry", "").strip()
        website = request.form.get("website", "").strip()
        description = request.form.get("description", "").strip()
        
        if not company_name:
            flash("Company name is required.", "error")
            return redirect(url_for("edit_company_profile"))
            
        logo_url = company["logo"]
        logo_file = request.files.get("logo")
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
        if logo_file and logo_file.filename:
            ext = logo_file.filename.rsplit(".", 1)[-1].lower()
            if ext in allowed_extensions:
                filename = f"company_{session['user_id']}_{int(time.time())}.{ext}"
                upload_path = os.path.join(BASE_DIR, "static", "uploads", filename)
                os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                logo_file.save(upload_path)
                logo_url = f"/static/uploads/{filename}"
                
                # Also update user avatar
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET avatar = %s WHERE id = %s", (logo_url, session["user_id"]))
                session["user_avatar"] = logo_url
                session.modified = True

        with conn.cursor() as cursor:
            # Update users table full_name
            cursor.execute("UPDATE users SET full_name = %s WHERE id = %s", (company_name, session["user_id"]))
            # Update companies table details
            cursor.execute("""
                UPDATE companies 
                SET company_name = %s, address = %s, pan_number = %s, industry = %s, website = %s, description = %s, logo = %s
                WHERE user_id = %s
            """, (company_name, address or None, pan_number or None, industry or None, website or None, description or None, logo_url, session["user_id"]))
            
        session["user_name"] = company_name
        session.modified = True
        flash("Company profile updated successfully.", "success")
        return redirect(url_for("company_profile", user_id=session["user_id"]))

    # Fetch company FAQs
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM company_faqs WHERE company_id = %s ORDER BY created_at ASC", (company["id"],))
        faqs = cursor.fetchall()

    return render_template("company_profile_edit.html", company=company, faqs=faqs)


@app.route("/company/faq/add", methods=["POST"])
@login_required
def add_company_faq():
    if session.get("account_type") != "company":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()
    
    if not question or not answer:
        return jsonify({"success": False, "message": "Question and answer are required."}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        return jsonify({"success": False, "message": "Company profile not found."}), 404
        
    company_id = company["id"]
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO company_faqs (company_id, question, answer) VALUES (%s, %s, %s)",
            (company_id, question, answer)
        )
        faq_id = cursor.lastrowid
        
    return jsonify({
        "success": True,
        "faq": {
            "id": faq_id,
            "question": question,
            "answer": answer
        }
    })


@app.route("/company/faq/delete/<int:faq_id>", methods=["POST"])
@login_required
def delete_company_faq(faq_id):
    if session.get("account_type") != "company":
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        
    if not company:
        return jsonify({"success": False, "message": "Company profile not found."}), 404
        
    company_id = company["id"]
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM company_faqs WHERE id = %s AND company_id = %s", (faq_id, company_id))
        
    return jsonify({"success": True})




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
            cursor.execute("SELECT COUNT(*) as count FROM bookmarks WHERE user_id = %s", (session["user_id"],))
            stats["bookmarks_count"] = cursor.fetchone()["count"]
            
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

            # 7. Detailed Applications (with job/company details) for Tracker
            cursor.execute("""
                SELECT a.id as application_id, a.status, a.created_at as applied_at,
                       j.id as job_id, j.title, j.opportunity_type, j.location, j.salary,
                       c.company_name, c.logo as company_logo
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                JOIN companies c ON j.company_id = c.id
                WHERE a.user_id = %s
                ORDER BY a.created_at DESC
            """, (session["user_id"],))
            applications = cursor.fetchall()

            # 8. Bookmarks (with job/company details)
            cursor.execute("""
                SELECT b.id as bookmark_id, b.created_at as bookmarked_at,
                       j.id as job_id, j.title, j.opportunity_type, j.location, j.salary,
                       c.company_name, c.logo as company_logo
                FROM bookmarks b
                JOIN jobs j ON b.job_id = j.id
                JOIN companies c ON j.company_id = c.id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
            """, (session["user_id"],))
            bookmarks = cursor.fetchall()
            
            # 9. Activities
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
                               activities=activities,
                               applications=applications,
                               bookmarks=bookmarks)



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
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, link)
            VALUES (%s, %s, %s, %s)
        """, (
            application["user_id"],
            "Application Status Updated",
            f"Your application for '{application['job_title']}' has been updated to '{new_status.capitalize()}'.",
            "/dashboard"
        ))
        
    try:
        from my_first_flask.utils.logger import log_activity
        log_activity("ATS Update", f"Applicant '{application['full_name']}' (ID: {application['user_id']}) moved to '{new_status}' for job '{application['job_title']}' by Company (ID: {company_id})")
    except Exception as e:
        print(f"Failed to log activity: {e}")
        
    return jsonify({"success": True, "message": f"Applicant moved to {new_status} successfully."})


@app.route("/dashboard/search")
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
        
    # Get applied and bookmarked job IDs for current candidate
    applied_job_ids = set()
    bookmarked_job_ids = set()
    profile_complete = False
    if session.get("account_type") == "individual":
        with conn.cursor() as cursor:
            cursor.execute("SELECT job_id FROM applications WHERE user_id = %s", (session["user_id"],))
            applied_job_ids = {row["job_id"] for row in cursor.fetchall()}
            
            cursor.execute("SELECT job_id FROM bookmarks WHERE user_id = %s", (session["user_id"],))
            bookmarked_job_ids = {row["job_id"] for row in cursor.fetchall()}
            
            cursor.execute("SELECT cv_path FROM users WHERE id = %s", (session["user_id"],))
            user_profile = cursor.fetchone()
            profile_complete = bool(user_profile and user_profile.get("cv_path"))

    # Also parse skills_required and questions for each job
    import json
    for opp in opportunities:
        opp["already_applied"] = opp["id"] in applied_job_ids
        opp["is_bookmarked"] = opp["id"] in bookmarked_job_ids
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
            
        with conn.cursor() as cursor:
            cursor.execute("SELECT question, answer FROM job_faqs WHERE job_id = %s", (opp["id"],))
            opp["faqs_list"] = cursor.fetchall()
            
            
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

        # Verify job exists
        cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "The opportunity you are applying for does not exist."}), 404

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


@app.route("/dashboard/jobs/bookmark/<int:job_id>", methods=["POST"])
@login_required
def dashboard_bookmark_toggle(job_id):
    # Allow any authenticated user to bookmark opportunities (not limited to 'individual' account type)
        
    conn = get_db()
    with conn.cursor() as cursor:
        # Check if job exists
        cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
        job = cursor.fetchone()
        if not job:
            return jsonify({"success": False, "message": "Opportunity not found."}), 404
            
        # Check existing bookmark
        cursor.execute("SELECT id FROM bookmarks WHERE user_id = %s AND job_id = %s", (session["user_id"], job_id))
        bookmark = cursor.fetchone()
        
        if bookmark:
            # Remove bookmark
            cursor.execute("DELETE FROM bookmarks WHERE user_id = %s AND job_id = %s", (session["user_id"], job_id))
            bookmarked = False
            message = "Bookmark removed."
            try:
                from my_first_flask.utils.logger import log_activity
                log_activity("Remove Bookmark", f"Candidate {session['user_name']} removed bookmark from job ID {job_id}")
            except Exception:
                pass
        else:
            # Add bookmark
            cursor.execute("INSERT INTO bookmarks (user_id, job_id) VALUES (%s, %s)", (session["user_id"], job_id))
            bookmarked = True
            message = "Opportunity saved successfully."
            try:
                from my_first_flask.utils.logger import log_activity
                log_activity("Add Bookmark", f"Candidate {session['user_name']} bookmarked job ID {job_id}")
            except Exception:
                pass
                
    return jsonify({"success": True, "bookmarked": bookmarked, "message": message})


@app.route("/dashboard/applications")
@login_required
def dashboard_applications():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id as application_id, a.status, a.created_at as applied_at,
               j.id as job_id, j.title, j.opportunity_type, j.location, j.salary,
               c.company_name, c.logo as company_logo
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        JOIN companies c ON j.company_id = c.id
        WHERE a.user_id = %s
        ORDER BY a.created_at DESC
    """, (session["user_id"],))
    applications = cursor.fetchall()
    return render_template("dashboard_applications.html", applications=applications)


@app.route("/dashboard/saved")
@login_required
def dashboard_saved():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id as bookmark_id, b.created_at as bookmarked_at,
               j.id as job_id, j.title, j.opportunity_type, j.location, j.salary,
               c.company_name, c.logo as company_logo
        FROM bookmarks b
        JOIN jobs j ON b.job_id = j.id
        JOIN companies c ON j.company_id = c.id
        WHERE b.user_id = %s
        ORDER BY b.created_at DESC
    """, (session["user_id"],))
    bookmarks = cursor.fetchall()
    
    cursor.execute("""
        SELECT id, search_query, opportunity_type, location, experience_level, email_alerts, created_at
        FROM saved_searches
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session["user_id"],))
    saved_searches = cursor.fetchall()
    
    return render_template("dashboard_saved.html", bookmarks=bookmarks, saved_searches=saved_searches)


@app.route("/dashboard/notifications")
@login_required
def dashboard_notifications():
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, title, message, link, is_read, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (session["user_id"],))
        notifications = cursor.fetchall()
    
    for notif in notifications:
        if notif.get("created_at"):
            notif["created_at_str"] = notif["created_at"].strftime("%Y-%m-%d %H:%M")
            
    return render_template("dashboard_notifications.html", notifications=notifications, active="notifications")


@app.route("/dashboard/saved-searches/save", methods=["POST"])
@login_required
def save_search():
    if session.get("account_type") != "individual":
        return jsonify({"success": False, "message": "Only candidate accounts can save searches."}), 403
        
    data = request.get_json() or {}
    query = data.get("query", "").strip() or None
    opp_type = data.get("type", "").strip() or None
    location = data.get("location", "").strip() or None
    experience = data.get("experience", "").strip() or None
    email_alerts = 1 if data.get("email_alerts") else 0

    if not query and not opp_type and not location and not experience:
        return jsonify({"success": False, "message": "Cannot save an empty search. Please specify at least one filter."}), 400

    conn = get_db()
    with conn.cursor() as cursor:
        # Check if already exists
        cursor.execute("""
            SELECT id FROM saved_searches 
            WHERE user_id = %s 
              AND (search_query = %s OR (search_query IS NULL AND %s IS NULL))
              AND (opportunity_type = %s OR (opportunity_type IS NULL AND %s IS NULL))
              AND (location = %s OR (location IS NULL AND %s IS NULL))
              AND (experience_level = %s OR (experience_level IS NULL AND %s IS NULL))
        """, (session["user_id"], query, query, opp_type, opp_type, location, location, experience, experience))
        
        if cursor.fetchone():
            return jsonify({"success": False, "message": "You have already saved this search!"})

        cursor.execute("""
            INSERT INTO saved_searches (user_id, search_query, opportunity_type, location, experience_level, email_alerts)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (session["user_id"], query, opp_type, location, experience, email_alerts))

    try:
        from my_first_flask.utils.logger import log_activity
        log_activity("Save Search", f"Candidate {session['user_name']} saved a new search with filters: query={query}, type={opp_type}, location={location}, experience={experience}, email_alerts={email_alerts}")
    except Exception:
        pass

    return jsonify({"success": True, "message": "Search saved successfully!"})


@app.route("/dashboard/saved-searches/delete/<int:search_id>", methods=["POST"])
@login_required
def delete_saved_search(search_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM saved_searches WHERE id = %s AND user_id = %s", (search_id, session["user_id"]))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Saved search not found."}), 404

        cursor.execute("DELETE FROM saved_searches WHERE id = %s AND user_id = %s", (search_id, session["user_id"]))

    try:
        from my_first_flask.utils.logger import log_activity
        log_activity("Delete Saved Search", f"Candidate {session['user_name']} deleted saved search ID {search_id}")
    except Exception:
        pass

    return jsonify({"success": True, "message": "Saved search deleted successfully."})


@app.route("/dashboard/saved-searches/toggle-alert/<int:search_id>", methods=["POST"])
@login_required
def toggle_search_alert(search_id):
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT email_alerts FROM saved_searches WHERE id = %s AND user_id = %s", (search_id, session["user_id"]))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Saved search not found."}), 404

        new_status = 0 if row["email_alerts"] else 1
        cursor.execute("UPDATE saved_searches SET email_alerts = %s WHERE id = %s AND user_id = %s", (new_status, search_id, session["user_id"]))

    try:
        from my_first_flask.utils.logger import log_activity
        log_activity("Toggle Search Alert", f"Candidate {session['user_name']} toggled email alerts to {new_status} for saved search ID {search_id}")
    except Exception:
        pass

    return jsonify({"success": True, "email_alerts": bool(new_status), "message": "Alert preference updated successfully."})



@app.route("/dashboard/settings")
@login_required
def dashboard_settings():
    return render_template("dashboard_settings.html")


@app.route("/dashboard/badges", methods=["GET", "POST"])
@login_required
def dashboard_badges():
    conn = get_db()
    account_type = session.get("account_type")
    
    if account_type == "company":
        with conn.cursor() as cursor:
            # Get company details
            cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
            company = cursor.fetchone()
            
            if not company:
                flash("Only registered companies can view or issue badges.", "error")
                return redirect(url_for("dashboard"))
                
            if request.method == "POST":
                candidate_email = request.form.get("candidate_email", "").strip().lower()
                badge_type = request.form.get("badge_type", "employment")
                title = request.form.get("title", "").strip()
                start_date = request.form.get("start_date")
                end_date = request.form.get("end_date") or None
                description = request.form.get("description", "").strip()
                
                # Validation
                if not candidate_email or not title or not start_date:
                    flash("Please fill in all required fields.", "error")
                    return redirect(url_for("dashboard_badges"))
                    
                # Find candidate
                cursor.execute("SELECT id, full_name FROM users WHERE email = %s AND account_type = 'individual'", (candidate_email,))
                candidate = cursor.fetchone()
                
                if not candidate:
                    flash(f"Candidate with email '{candidate_email}' was not found or is a company account.", "error")
                    return redirect(url_for("dashboard_badges"))
                    
                # Insert badge
                cursor.execute("""
                    INSERT INTO user_badges (user_id, company_id, title, badge_type, description, start_date, end_date, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
                """, (candidate["id"], company["id"], title, badge_type, description or None, start_date, end_date))
                
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, link)
                    VALUES (%s, %s, %s, %s)
                """, (
                    candidate["id"],
                    "New Badge Verification Request",
                    f"Company '{session['user_name']}' has issued you a professional verification badge request: '{title}'.",
                    "/dashboard/badges"
                ))
                
                flash(f"Verification badge successfully issued to {candidate['full_name']}!", "success")
                return redirect(url_for("dashboard_badges"))
            
            # Fetch issued badges
            cursor.execute("""
                SELECT b.*, u.full_name as candidate_name, u.email as candidate_email
                FROM user_badges b
                JOIN users u ON b.user_id = u.id
                WHERE b.company_id = %s
                ORDER BY b.awarded_at DESC
            """, (company["id"],))
            issued_badges = cursor.fetchall()
            
            return render_template("dashboard_badges.html", issued_badges=issued_badges)
            
    else: # Individual / Candidate
        with conn.cursor() as cursor:
            # Fetch pending badges
            cursor.execute("""
                SELECT b.*, c.company_name, c.logo as company_logo
                FROM user_badges b
                JOIN companies c ON b.company_id = c.id
                WHERE b.user_id = %s AND b.status = 'pending'
                ORDER BY b.awarded_at DESC
            """, (session["user_id"],))
            pending_badges = cursor.fetchall()
            
            # Fetch active (accepted) badges
            cursor.execute("""
                SELECT b.*, c.company_name, c.logo as company_logo
                FROM user_badges b
                JOIN companies c ON b.company_id = c.id
                WHERE b.user_id = %s AND b.status = 'accepted'
                ORDER BY b.awarded_at DESC
            """, (session["user_id"],))
            active_badges = cursor.fetchall()
            
            return render_template("dashboard_badges.html", pending_badges=pending_badges, active_badges=active_badges)


@app.route("/dashboard/badges/accept/<int:badge_id>", methods=["POST"])
@login_required
def accept_badge(badge_id):
    conn = get_db()
    user_id = session["user_id"]
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM user_badges WHERE id = %s AND user_id = %s AND status = 'pending'", (badge_id, user_id))
        badge = cursor.fetchone()
        
        if badge:
            cursor.execute("UPDATE user_badges SET status = 'accepted' WHERE id = %s", (badge_id,))
            cursor.execute("""
                SELECT b.title, c.user_id as company_user_id
                FROM user_badges b
                JOIN companies c ON b.company_id = c.id
                WHERE b.id = %s
            """, (badge_id,))
            badge_info = cursor.fetchone()
            if badge_info:
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, link)
                    VALUES (%s, %s, %s, %s)
                """, (
                    badge_info["company_user_id"],
                    "Badge Verification Accepted",
                    f"Candidate '{session['user_name']}' has accepted the verification badge: '{badge_info['title']}'.",
                    "/dashboard/badges"
                ))
            flash("Badge successfully accepted and added to your public profile!", "success")
        else:
            flash("Unable to accept badge.", "error")
            
    return redirect(url_for("dashboard_badges"))


@app.route("/dashboard/badges/reject/<int:badge_id>", methods=["POST"])
@login_required
def reject_badge(badge_id):
    conn = get_db()
    user_id = session["user_id"]
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM user_badges WHERE id = %s AND user_id = %s AND status = 'pending'", (badge_id, user_id))
        badge = cursor.fetchone()
        
        if badge:
            cursor.execute("UPDATE user_badges SET status = 'rejected' WHERE id = %s", (badge_id,))
            cursor.execute("""
                SELECT b.title, c.user_id as company_user_id
                FROM user_badges b
                JOIN companies c ON b.company_id = c.id
                WHERE b.id = %s
            """, (badge_id,))
            badge_info = cursor.fetchone()
            if badge_info:
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, link)
                    VALUES (%s, %s, %s, %s)
                """, (
                    badge_info["company_user_id"],
                    "Badge Verification Rejected",
                    f"Candidate '{session['user_name']}' has rejected the verification badge: '{badge_info['title']}'.",
                    "/dashboard/badges"
                ))
            flash("Badge verification request rejected.", "info")
        else:
            flash("Unable to reject badge.", "error")
            
    return redirect(url_for("dashboard_badges"))



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
    if session.get("account_type") not in ("individual", "admin"):
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
    if session.get("account_type") not in ("individual", "admin"):
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
    if session.get("account_type") not in ("individual", "admin"):
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


def extract_text_from_pdf(filepath):
    """Extracts text content from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return ""


def query_gemini_resume_analysis(resume_text, job_description=""):
    """Queries Gemini 1.5 Flash API to perform resume diagnostics returning JSON."""
    import urllib.request
    import json
    
    if not config.GEMINI_API_KEY:
        return {"error": "Gemini API key is not configured in settings."}
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GEMINI_API_KEY}"
    
    prompt = f"""
    You are an expert ATS (Applicant Tracking System) scanner and career coach.
    Analyze the following resume text and optionally the targeted job description.
    
    RESUME TEXT:
    {resume_text}
    
    TARGET JOB DESCRIPTION:
    {job_description}
    
    You must output a raw JSON object matching the following structure:
    {{
      "overall_score": <int 0 to 100>,
      "categories": {{
        "formatting": <int 0 to 100>,
        "impact": <int 0 to 100>,
        "skills": <int 0 to 100>,
        "experience": <int 0 to 100>
      }},
      "feedback": {{
        "formatting": [<strings of constructive feedback>],
        "impact": [<strings of constructive feedback>],
        "skills": [<strings of constructive feedback>],
        "experience": [<strings of constructive feedback>]
      }},
      "rewrites": [
        {{
          "original": "<original weak line from the experience section>",
          "improved": "<improved strong line using action verbs and quantifiable results>",
          "reason": "<explanation of why the improvement works>"
        }}
      ],
      "keyword_scan": {{
        "matched_keywords": [<list of matching skills/keywords between resume and job description>],
        "missing_keywords": [<list of critical missing skills/keywords based on the job description>]
      }}
    }}
    
    Ensure categories scoring is realistic (most resumes score between 50 and 85).
    Ensure the JSON response is valid and strictly parsed.
    Do not add any markup or markdown wraps around the JSON object.
    """
    
    req_data = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_body = json.dumps(req_data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text_response)
    except Exception as e:
        print(f"Error querying Gemini API: {e}")
        return {"error": f"Failed to get analysis: {str(e)}"}


@app.route("/dashboard/resume-doctor", methods=["GET"])


@login_required
def dashboard_resume_doctor():
    if session.get("account_type") not in ("individual", "admin"):
        flash("Only individuals can access the Resume Doctor.", "error")
        return redirect(url_for("dashboard"))
        
    import json
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT resume_analysis FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
        
    analysis = None
    if user and user["resume_analysis"]:
        try:
            analysis = json.loads(user["resume_analysis"])
        except Exception:
            analysis = None
            
    return render_template("dashboard_resume_doctor.html", active="resume_doctor", analysis=analysis)


@app.route("/dashboard/resume-doctor/analyze", methods=["POST"])
@login_required
def dashboard_resume_doctor_analyze():
    """
    POST route to trigger AI resume diagnostic analysis.
    Extracts text content from either dynamically built resume JSON data 
    or an uploaded PDF resume, queries the Gemini API, and saves the cached 
    review JSON back to the user's DB entry.
    """
    if session.get("account_type") not in ("individual", "admin"):
        flash("Only individuals can use the Resume Doctor.", "error")
        return redirect(url_for("dashboard"))
        
    import json
    
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT cv_path, cv_data FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
        
    if not user or (not user["cv_path"] and not user["cv_data"]):
        flash("Please build or upload a CV first before using the Resume Doctor.", "error")
        return redirect(url_for("dashboard_cv"))
        
    resume_text = ""
    cv_data_str = user["cv_data"]
    cv_path = user["cv_path"]
    
    if cv_data_str and cv_data_str != "{}":
        try:
            cv_dict = json.loads(cv_data_str)
            resume_parts = []
            if cv_dict.get("full_name"): resume_parts.append(f"Name: {cv_dict['full_name']}")
            if cv_dict.get("email"): resume_parts.append(f"Email: {cv_dict['email']}")
            if cv_dict.get("portfolio"): resume_parts.append(f"Portfolio: {cv_dict['portfolio']}")
            if cv_dict.get("github"): resume_parts.append(f"GitHub: {cv_dict['github']}")
            if cv_dict.get("linkedin"): resume_parts.append(f"LinkedIn: {cv_dict['linkedin']}")
            
            if cv_dict.get("education"):
                resume_parts.append("\nEDUCATION:")
                for edu in cv_dict["education"]:
                    resume_parts.append(f"- {edu.get('degree')} at {edu.get('school')}. Details: {edu.get('details')}")
                    
            if cv_dict.get("experience"):
                resume_parts.append("\nWORK EXPERIENCE:")
                for exp in cv_dict["experience"]:
                    resume_parts.append(f"- {exp.get('title')} at {exp.get('company')} ({exp.get('dates')}). Description: {exp.get('description')}")
                    
            if cv_dict.get("projects"):
                resume_parts.append("\nPROJECTS:")
                for proj in cv_dict["projects"]:
                    resume_parts.append(f"- {proj.get('title')} [{proj.get('tag')}]. Link: {proj.get('link')}. Description: {proj.get('description')}")
                    
            if cv_dict.get("skills"):
                resume_parts.append("\nSKILLS:")
                for sk in cv_dict["skills"]:
                    resume_parts.append(f"- {sk.get('category')}: {sk.get('list')}")
                    
            if cv_dict.get("certifications"):
                resume_parts.append("\nCERTIFICATIONS:")
                for cert in cv_dict["certifications"]:
                    resume_parts.append(f"- {cert}")
                    
            resume_text = "\n".join(resume_parts)
        except Exception as e:
            print(f"Error parsing cv_data JSON: {e}")
            
    if not resume_text and cv_path:
        full_path = os.path.join(BASE_DIR, cv_path.lstrip("/"))
        if os.path.exists(full_path):
            if cv_path.lower().endswith(".pdf"):
                resume_text = extract_text_from_pdf(full_path)
            else:
                resume_text = f"Uploaded File: {os.path.basename(full_path)}"
                
    if not resume_text.strip():
        flash("Could not extract readable text from your resume. If you uploaded an image or scanned document, please build it dynamically in the CV Builder.", "error")
        return redirect(url_for("dashboard_resume_doctor"))
        
    job_description = request.form.get("job_description", "").strip()
    
    analysis_result = query_gemini_resume_analysis(resume_text, job_description)
    
    if "error" in analysis_result:
        flash(analysis_result["error"], "error")
        return redirect(url_for("dashboard_resume_doctor"))
        
    analysis_str = json.dumps(analysis_result)
    with conn.cursor() as cursor:
        cursor.execute("UPDATE users SET resume_analysis = %s WHERE id = %s", (analysis_str, session["user_id"]))
        
    flash("Resume diagnostic review successfully completed!", "success")
    return redirect(url_for("dashboard_resume_doctor"))




@app.route("/dashboard/events")
def dashboard_events():
    conn = get_db()
    account_type = session.get("account_type")
    
    with conn.cursor() as cursor:
        if account_type == "company":
            cursor.execute(
                "SELECT e.*, c.company_name, c.logo "
                "FROM events e "
                "JOIN companies c ON e.company_id = c.id "
                "WHERE c.user_id = %s "
                "ORDER BY e.event_date ASC",
                (session["user_id"],)
            )
        else:
            cursor.execute(
                "SELECT e.*, c.company_name, c.logo "
                "FROM events e "
                "JOIN companies c ON e.company_id = c.id "
                "ORDER BY e.event_date ASC"
            )
        events = cursor.fetchall()
        
    return render_template("dashboard_events.html", events=events)


@app.route("/dashboard/events/create", methods=["GET", "POST"])
@login_required
def dashboard_create_event():
    if session.get("account_type") != "company":
        return redirect(url_for("dashboard_events"))
        
    error = None
    form_data = {}
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date_str = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()
        registration_link = request.form.get("registration_link", "").strip() or None
        
        form_data = {
            "title": title,
            "description": description,
            "event_date": event_date_str,
            "location": location,
            "registration_link": registration_link
        }
        
        if not title:
            error = "Event title is required."
        elif not description:
            error = "Event description is required."
        elif not event_date_str:
            error = "Event date and time is required."
        elif not location:
            error = "Event location is required."
        else:
            try:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%dT%H:%M")
                conn = get_db()
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
                    company = cursor.fetchone()
                
                if not company:
                    error = "Company profile not found. Please register as a company first."
                else:
                    company_id = company["id"]
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO events (company_id, title, description, event_date, location, registration_link) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (company_id, title, description, event_date, location, registration_link)
                        )
                    flash("Event created successfully!", "success")
                    return redirect(url_for("dashboard_events"))
            except ValueError:
                error = "Invalid date and time format."
            except Exception as e:
                error = f"An error occurred: {str(e)}"
                
    return render_template("dashboard_create_event.html", form_data=form_data, error=error)


@app.route("/dashboard/events/edit/<int:event_id>", methods=["GET", "POST"])
@login_required
def dashboard_edit_event(event_id):
    if session.get("account_type") != "company":
        return redirect(url_for("dashboard_events"))

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()

    if not company:
        flash("Company profile not found.", "error")
        return redirect(url_for("dashboard_events"))

    company_id = company["id"]

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM events WHERE id = %s AND company_id = %s", (event_id, company_id))
        event = cursor.fetchone()

    if not event:
        flash("Event not found or unauthorized.", "error")
        return redirect(url_for("dashboard_events"))

    error = None
    form_data = {
        "title": event["title"],
        "description": event["description"],
        "event_date": event["event_date"].strftime("%Y-%m-%dT%H:%M") if event["event_date"] else "",
        "location": event["location"],
        "registration_link": event["registration_link"]
    }

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date_str = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()
        registration_link = request.form.get("registration_link", "").strip() or None

        form_data = {
            "title": title,
            "description": description,
            "event_date": event_date_str,
            "location": location,
            "registration_link": registration_link
        }

        if not title:
            error = "Event title is required."
        elif not description:
            error = "Event description is required."
        elif not event_date_str:
            error = "Event date and time is required."
        elif not location:
            error = "Event location is required."
        else:
            try:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%dT%H:%M")
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE events SET title = %s, description = %s, event_date = %s, location = %s, registration_link = %s WHERE id = %s AND company_id = %s",
                        (title, description, event_date, location, registration_link, event_id, company_id)
                    )
                flash("Event updated successfully!", "success")
                return redirect(url_for("dashboard_events"))
            except ValueError:
                error = "Invalid date and time format."
            except Exception as e:
                error = f"An error occurred: {str(e)}"

    return render_template("dashboard_create_event.html", form_data=form_data, error=error, is_edit=True, event_id=event_id)


@app.route("/dashboard/events/delete/<int:event_id>", methods=["POST"])
@login_required
def dashboard_delete_event(event_id):
    if session.get("account_type") != "company":
        return redirect(url_for("dashboard_events"))

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()

    if not company:
        flash("Company profile not found.", "error")
        return redirect(url_for("dashboard_events"))

    company_id = company["id"]

    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM events WHERE id = %s AND company_id = %s", (event_id, company_id))

    flash("Event deleted successfully!", "success")
    return redirect(url_for("dashboard_events"))


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
            
        if opportunity_type not in ["job", "internship"]:
            flash("Invalid opportunity type selection.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        if not city:
            flash("City location is required.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        if not min_salary:
            flash("Minimum salary compensation is required.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        if opportunity_type == "job" and not min_exp:
            flash("Minimum experience requirement is required for Job posts.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        conn = get_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, company_name FROM companies WHERE user_id = %s", (session["user_id"],))
            company = cursor.fetchone()
            
        if not company:
            flash("Please complete your company profile before posting an opportunity.", "error")
            return redirect(url_for("profile"))
            
        import pymysql
        try:
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
                job_id = cursor.lastrowid
                if not job_id:
                    raise pymysql.MySQLError("Failed to retrieve generated job ID.")

                # Parse and insert FAQs
                faq_qs = request.form.getlist("faq_questions[]")
                faq_as = request.form.getlist("faq_answers[]")
                for i in range(min(len(faq_qs), len(faq_as))):
                    fq = faq_qs[i].strip() if faq_qs[i] else ""
                    fa = faq_as[i].strip() if faq_as[i] else ""
                    if fq and fa:
                        cursor.execute(
                            "INSERT INTO job_faqs (job_id, question, answer) VALUES (%s, %s, %s)",
                            (job_id, fq, fa)
                        )
        except pymysql.MySQLError as db_err:
            print(f"[DATABASE ERROR] Failed to insert job/faqs: {db_err}")
            try:
                from my_first_flask.utils.logger import log_activity
                log_activity("Database Error", f"Failed to post opportunity '{title}': {db_err}")
            except Exception:
                pass
            flash("A database error occurred while publishing the opportunity. Please try again.", "error")
            return render_template("dashboard_post_opportunity.html")
            
        # Log job posting event
        print(f"[JOB LOG] User {session['user_id']} ({company['company_name']}) posted a new {opportunity_type}: '{title}' at {location}")
        try:
            from my_first_flask.utils.logger import log_activity
            log_activity("Post Opportunity", f"Company '{company['company_name']}' (ID: {company['id']}) posted a new {opportunity_type}: '{title}' at {location}")
        except Exception as log_err:
            print(f"Failed to write post job log: {log_err}")

        # Check matching saved searches for job alerts
        try:
            with conn.cursor() as cursor:
                # Get all saved searches with email alerts active
                # Get all saved searches for active matching notifications
                cursor.execute("""
                    SELECT s.*, u.email as user_email, u.full_name as user_name
                    FROM saved_searches s
                    JOIN users u ON s.user_id = u.id
                    WHERE u.is_banned = 0
                """)
                active_alerts = cursor.fetchall()
                
                for alert in active_alerts:
                    match = True
                    
                    # 1. Match search query (case-insensitive) against job title, description, skills
                    if alert.get("search_query"):
                        sq = alert["search_query"].lower()
                        # check title, description, skills
                        in_title = sq in title.lower()
                        in_desc = sq in description.lower()
                        in_skills = sq in (skills_required or "").lower()
                        if not (in_title or in_desc or in_skills):
                            match = False
                            
                    # 2. Match opportunity type
                    if match and alert.get("opportunity_type"):
                        if alert["opportunity_type"].lower() != opportunity_type.lower():
                            match = False
                            
                    # 3. Match location (fuzzy search/substring matching)
                    if match and alert.get("location"):
                        # check if alert location matches job location
                        alert_loc = alert["location"].strip().lower()
                        if alert_loc and alert_loc not in location.lower():
                            match = False
                            
                    # 4. Match experience level
                    if match and alert.get("experience_level"):
                        # check if alert experience_level matches job experience_level
                        alert_exp = alert["experience_level"].strip().lower()
                        if alert_exp and alert_exp not in experience_level.lower():
                            match = False
                            
                    if match:
                        # Create in-app notification
                        cursor.execute("""
                            INSERT INTO notifications (user_id, title, message, link)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            alert["user_id"],
                            "Opportunity Match",
                            f"New {opportunity_type.capitalize()} '{title}' matching your saved search '{alert['search_query'] or ''}' has been posted by {company['company_name']}.",
                            f"/dashboard/search?q={alert['search_query'] or ''}"
                        ))
                        
                        # Send email alert to user if enabled!
                        if alert.get("email_alerts") == 1:
                            # Prepare HTML content
                            alert_email_html = f"""
                            <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;">
                                <div style="text-align: center; border-bottom: 2px solid #2456ff; padding-bottom: 15px; margin-bottom: 20px;">
                                    <h1 style="color: #05154b; font-size: 24px; margin: 0;">Talent Khoj</h1>
                                    <p style="color: #64748b; font-size: 14px; margin: 5px 0 0;">New Opportunity Match Alert!</p>
                                </div>
                                <p style="font-size: 16px; color: #1e293b;">Hi {alert['user_name']},</p>
                                <p style="font-size: 15px; color: #334155; line-height: 1.6;">
                                    A new opportunity matching your saved search preferences has been posted on Talent Khoj.
                                </p>
                                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 20px 0;">
                                    <h2 style="font-size: 18px; color: #0f172a; margin: 0 0 10px;">{title}</h2>
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #475569;"><strong>Company:</strong> {company['company_name']}</p>
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #475569;"><strong>Location:</strong> {location}</p>
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #475569;"><strong>Type:</strong> <span style="text-transform: capitalize;">{opportunity_type}</span></p>
                                    <p style="margin: 0 0 8px; font-size: 14px; color: #475569;"><strong>Salary:</strong> {salary}</p>
                                    <p style="margin: 0; font-size: 14px; color: #475569;"><strong>Required Experience:</strong> {experience_level}</p>
                                </div>
                                <div style="text-align: center; margin-top: 30px;">
                                    <a href="http://127.0.0.1:5000/dashboard/search?q={alert['search_query'] or ''}" style="background: #2456ff; color: white; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: bold; font-size: 15px; display: inline-block;">View Opportunity</a>
                                </div>
                                <hr style="border: none; border-top: 1px solid #f1f5f9; margin: 30px 0 20px;">
                                <p style="font-size: 12px; color: #94a3b8; text-align: center; line-height: 1.5;">
                                    You are receiving this because you enabled email alerts for your saved search on Talent Khoj.<br>
                                    <a href="http://127.0.0.1:5000/dashboard/saved" style="color: #2456ff; text-decoration: underline;">Manage Alert Settings</a>
                                </p>
                            </div>
                            """
                            
                            EmailService.send_email(
                                to=alert["user_email"],
                                subject=f"Job Alert: New {opportunity_type.capitalize()} matching your search - {title}",
                                html=alert_email_html
                            )
        except Exception as alert_err:
            print(f"Failed to process job alert notifications: {alert_err}")
        
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


@app.route("/dashboard/inbox", methods=["GET"])
@login_required
def dashboard_inbox():
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                u.id AS other_user_id,
                u.full_name AS other_user_name,
                u.avatar AS other_user_avatar,
                u.account_type AS other_user_account_type,
                m.message_text AS last_message,
                m.created_at AS last_message_time,
                (SELECT COUNT(*) FROM messages WHERE sender_id = u.id AND receiver_id = %s AND is_read = 0) AS unread_count
            FROM (
                SELECT 
                    CASE WHEN sender_id = %s THEN receiver_id ELSE sender_id END AS chat_user_id,
                    MAX(created_at) AS max_time
                FROM messages
                WHERE sender_id = %s OR receiver_id = %s
                GROUP BY chat_user_id
            ) latest
            JOIN messages m ON ((m.sender_id = %s AND m.receiver_id = latest.chat_user_id) 
                            OR (m.sender_id = latest.chat_user_id AND m.receiver_id = %s)) 
                            AND m.created_at = latest.max_time
            JOIN users u ON u.id = latest.chat_user_id
            ORDER BY last_message_time DESC
        """, (user_id, user_id, user_id, user_id, user_id, user_id))
        conversations = cursor.fetchall()

    for conv in conversations:
        if conv.get("last_message_time"):
            conv["last_message_time"] = conv["last_message_time"].strftime("%Y-%m-%d %H:%M")

    return render_template("dashboard_inbox.html", conversations=conversations, active="inbox")


@app.route("/dashboard/headhunt", methods=["GET"])
@login_required
def dashboard_headhunt():
    if session.get("account_type") != "company":
        flash("Access denied. The headhunting directory is only accessible by recruiters.", "error")
        return redirect(url_for("dashboard"))

    query_param = request.args.get("q", "").strip()
    status_param = request.args.get("status", "").strip()
    location_param = request.args.get("location", "").strip()

    conn = get_db()
    with conn.cursor() as cursor:
        sql = """
            SELECT id, full_name, avatar, bio, location, skills, active_status 
            FROM users 
            WHERE account_type = 'individual' AND headhunting_mode = 1
        """
        params = []

        if query_param:
            sql += " AND (full_name LIKE %s OR bio LIKE %s OR skills LIKE %s)"
            like_val = f"%{query_param}%"
            params.extend([like_val, like_val, like_val])

        if status_param:
            sql += " AND active_status = %s"
            params.append(status_param)

        if location_param:
            sql += " AND location LIKE %s"
            params.append(f"%{location_param}%")

        sql += " ORDER BY full_name ASC"
        cursor.execute(sql, tuple(params))
        candidates = cursor.fetchall()

        # Get distinct locations for filter dropdown
        cursor.execute("""
            SELECT DISTINCT location 
            FROM users 
            WHERE account_type = 'individual' AND headhunting_mode = 1 AND location IS NOT NULL AND location != ''
            ORDER BY location ASC
        """)
        locations = [row["location"] for row in cursor.fetchall()]

    return render_template(
        "dashboard_headhunt.html",
        candidates=candidates,
        locations=locations,
        query=query_param,
        status=status_param,
        selected_location=location_param,
        active="headhunt"
    )


# ─── MESSAGING API ───────────────────────────────────────────────────────────

@app.route("/api/messages/send", methods=["POST"])
@login_required
def api_send_message():
    data = request.get_json() or {}
    receiver_id = data.get("receiver_id")
    message_text = data.get("message_text", "").strip()

    if not receiver_id or not message_text:
        return jsonify({"success": False, "error": "Receiver ID and message text are required"}), 400

    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE id = %s", (receiver_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Receiver not found"}), 404

        cursor.execute(
            "INSERT INTO messages (sender_id, receiver_id, message_text) VALUES (%s, %s, %s)",
            (session["user_id"], receiver_id, message_text)
        )
    return jsonify({"success": True, "message": "Message sent!"})


@app.route("/api/messages/thread/<int:other_user_id>", methods=["GET"])
@login_required
def api_get_message_thread(other_user_id):
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE messages SET is_read = 1 WHERE sender_id = %s AND receiver_id = %s AND is_read = 0",
            (other_user_id, user_id)
        )
        
        cursor.execute("""
            SELECT m.id, m.sender_id, m.receiver_id, m.message_text, m.is_read, m.created_at,
                   u.full_name AS sender_name, u.avatar AS sender_avatar
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE (m.sender_id = %s AND m.receiver_id = %s)
               OR (m.sender_id = %s AND m.receiver_id = %s)
            ORDER BY m.created_at ASC
        """, (user_id, other_user_id, other_user_id, user_id))
        messages = cursor.fetchall()

    for msg in messages:
        if msg.get("created_at"):
            msg["created_at"] = msg["created_at"].strftime("%Y-%m-%d %H:%M")

    return jsonify({"success": True, "messages": messages})


@app.route("/api/messages/unread-count", methods=["GET"])
@login_required
def api_unread_count():
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM messages WHERE receiver_id = %s AND is_read = 0", (user_id,))
        row = cursor.fetchone()
    return jsonify({"success": True, "unread_count": row["count"] if row else 0})

@app.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, title, message, link, is_read, created_at
            FROM notifications
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (user_id,))
        notifications = cursor.fetchall()

    for notif in notifications:
        if notif.get("created_at"):
            notif["created_at"] = notif["created_at"].strftime("%Y-%m-%d %H:%M")

    return jsonify({"success": True, "notifications": notifications})


@app.route("/api/notifications/unread-count", methods=["GET"])
@login_required
def api_get_unread_notifications_count():
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) as unread_count
            FROM notifications
            WHERE user_id = %s AND is_read = 0
        """, (user_id,))
        row = cursor.fetchone()
    return jsonify({"success": True, "unread_count": row["unread_count"] if row else 0})


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_mark_all_notifications_read():
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE user_id = %s
        """, (user_id,))
    return jsonify({"success": True, "message": "All notifications marked as read."})


@app.route("/api/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
def api_mark_notification_read(notif_id):
    user_id = session["user_id"]
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s AND user_id = %s
        """, (notif_id, user_id))
    return jsonify({"success": True, "message": "Notification marked as read."})

@app.route("/reviews/submit", methods=["POST"])
@login_required
def submit_review():
    reviewer_id = session.get("user_id")
    reviewer_type = session.get("account_type")
    
    reviewee_id = request.form.get("reviewee_id")
    rating_str = request.form.get("rating")
    comment = request.form.get("comment", "").strip()
    
    if not reviewee_id or not rating_str or not comment:
        flash("All fields are required.", "error")
        return redirect(request.referrer or url_for("home"))
        
    try:
        reviewee_id = int(reviewee_id)
        rating = int(rating_str)
    except ValueError:
        flash("Invalid input data.", "error")
        return redirect(request.referrer or url_for("home"))
        
    if reviewer_id == reviewee_id:
        flash("You cannot review yourself.", "error")
        return redirect(request.referrer or url_for("home"))
        
    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "error")
        return redirect(request.referrer or url_for("home"))
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT account_type FROM users WHERE id = %s", (reviewee_id,))
        reviewee = cursor.fetchone()
        
    if not reviewee:
        flash("User not found.", "error")
        return redirect(request.referrer or url_for("home"))
        
    reviewee_type = reviewee["account_type"]
    
    if reviewer_type == "company" and reviewee_type != "individual":
        flash("Companies can only review individual candidates.", "error")
        return redirect(request.referrer or url_for("home"))
    elif reviewer_type == "individual" and reviewee_type != "company":
        flash("Candidates can only review companies.", "error")
        return redirect(request.referrer or url_for("home"))
        
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM reviews WHERE reviewer_id = %s AND reviewee_id = %s",
            (reviewer_id, reviewee_id)
        )
        existing_review = cursor.fetchone()
        
        if existing_review:
            cursor.execute(
                "UPDATE reviews SET rating = %s, comment = %s, created_at = CURRENT_TIMESTAMP WHERE id = %s",
                (rating, comment, existing_review["id"])
            )
            flash("Your review has been updated.", "success")
        else:
            cursor.execute(
                "INSERT INTO reviews (reviewer_id, reviewee_id, rating, comment) VALUES (%s, %s, %s, %s)",
                (reviewer_id, reviewee_id, rating, comment)
            )
            flash("Review submitted successfully.", "success")
            
    if reviewee_type == "company":
        return redirect(url_for("company_profile", user_id=reviewee_id))
    else:
        return redirect(url_for("user_profile", user_id=reviewee_id))


def log_admin_action(action, target_type, target_id, details):
    """Helper function to log admin operations into the database."""
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO admin_logs (admin_name, action, target_type, target_id, details) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session.get("user_name", "System"), action, target_type, target_id, details)
        )


# ─── ADMIN DASHBOARD ─────────────────────────────────────────────────────────

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    with conn.cursor() as cursor:
        # Total Users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_users = cursor.fetchone()["count"]

        # Suspended Users
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_banned = 1")
        suspended_users = cursor.fetchone()["count"]

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
        suspended_users=suspended_users,
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
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM reports")
        total_reports = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM reports WHERE status = 'Pending'")
        pending_reports = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM reports WHERE status = 'Resolved'")
        resolved_reports = cursor.fetchone()["count"]
        
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT r.id, r.type, r.content, r.status, r.created_at, u.full_name as user 
            FROM reports r 
            LEFT JOIN users u ON r.user_id = u.id 
            ORDER BY r.created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
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
            
    total_pages = max(1, (total_reports + per_page - 1) // per_page)
            
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_report.html",
        total_reports=total_reports,
        pending_reports=pending_reports,
        resolved_reports=resolved_reports,
        reports=reports_list,
        current_user=CurrentUserMock(),
        page=page,
        total_pages=total_pages,
        total_count=total_reports,
        per_page=per_page
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
    
    log_admin_action("delete_reports", "report", 0, f"Deleted report IDs: {report_ids}")
    return jsonify({"success": True, "message": "Selected reports deleted successfully."})


@app.route("/admin/users")
@admin_required
def admin_users():
    search = request.args.get("search", "").strip()
    role_filter = request.args.get("role", "").strip()
    status_filter = request.args.get("status", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20

    conn = get_db()
    base_query = "FROM users"
    params = []
    conditions = []
    if search:
        conditions.append("(full_name LIKE %s OR email LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if role_filter:
        conditions.append("account_type = %s")
        params.append(role_filter)
    if status_filter == "suspended":
        conditions.append("is_banned = 1")
    elif status_filter == "active":
        conditions.append("is_banned = 0")
    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) as cnt {base_query}", tuple(params))
        total_count = cursor.fetchone()["cnt"]

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT id, full_name, email, account_type, verified, is_banned, ban_reason, created_at {base_query} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (per_page, offset)
        )
        db_users = cursor.fetchall()

    users_list = [{
        "id": u["id"], "full_name": u["full_name"], "email": u["email"],
        "account_type": u["account_type"], "verified": u["verified"],
        "is_banned": u.get("is_banned", 0), "ban_reason": u.get("ban_reason", ""),
        "date": u["created_at"].strftime("%b %d, %Y") if u["created_at"] else ""
    } for u in db_users]

    class CurrentUserMock:
        username = session.get("user_name", "Admin")

    return render_template(
        "admin_users.html",
        users=users_list,
        search=search,
        selected_role=role_filter,
        selected_status=status_filter,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page,
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
        cursor.execute("SELECT full_name FROM users WHERE id = %s", (user_id,))
        target = cursor.fetchone()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

    log_admin_action("delete_user", "user", user_id, f"Deleted user: {target['full_name'] if target else user_id}")
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

    log_admin_action("change_role", "user", user_id, f"Changed role to {new_role}")
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
    log_admin_action("ban_user", "user", user_id, f"Suspended: {user['full_name']} — {reason}")
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
    log_admin_action("unban_user", "user", user_id, f"Reinstated: {user['full_name']}")
    return jsonify({"success": True, "message": f"User '{user['full_name']}' has been reinstated."})


# ─── ADMIN LOGS PAGE (Commit 5) ───────────────────────────────────────────────

@app.route("/admin/logs")
@admin_required
def admin_logs():
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30
    action_filter = request.args.get("action", "").strip()

    conn = get_db()
    base = "FROM admin_logs"
    params = []
    if action_filter:
        base += " WHERE action = %s"
        params.append(action_filter)

    with conn.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) as cnt {base}", tuple(params))
        total_count = cursor.fetchone()["cnt"]

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT id, admin_name, action, target_type, target_id, details, created_at {base} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (per_page, offset)
        )
        logs_raw = cursor.fetchall()

    logs = [{
        "id": r["id"],
        "admin_name": r["admin_name"] or "System",
        "action": r["action"],
        "target_type": r["target_type"] or "-",
        "target_id": r["target_id"],
        "details": r["details"] or "-",
        "date": r["created_at"].strftime("%b %d, %Y %H:%M") if r["created_at"] else ""
    } for r in logs_raw]

    # Distinct actions for filter dropdown
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT action FROM admin_logs ORDER BY action")
        actions = [r["action"] for r in cursor.fetchall()]

    class CurrentUserMock:
        username = session.get("user_name", "Admin")

    return render_template(
        "admin_logs.html",
        logs=logs,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page,
        action_filter=action_filter,
        actions=actions,
        current_user=CurrentUserMock()
    )


# ─── CSV EXPORT (Commit 6) ────────────────────────────────────────────────────

@app.route("/admin/users/export")
@admin_required
def export_users_csv():
    import csv, io
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, full_name, email, account_type, verified, is_banned, ban_reason, created_at
            FROM users ORDER BY created_at DESC
        """)
        users = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Full Name", "Email", "Role", "Verified", "Banned", "Ban Reason", "Joined Date"])
    for u in users:
        writer.writerow([
            u["id"],
            u["full_name"],
            u["email"],
            u["account_type"],
            "Yes" if u.get("verified") else "No",
            "Yes" if u.get("is_banned") else "No",
            u.get("ban_reason") or "",
            u["created_at"].strftime("%Y-%m-%d %H:%M") if u["created_at"] else ""
        ])

    output.seek(0)
    from flask import Response
    from datetime import date
    filename = f"talentkhoj_users_{date.today()}.csv"
    log_admin_action("export_csv", "users", None, f"Exported {len(users)} users to CSV")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


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
    page = max(1, int(request.args.get("page", 1)))
    per_page = 20
    
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM jobs")
        total_count = cursor.fetchone()["count"]
        
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT j.id, j.title, j.opportunity_type, j.location, j.salary, j.created_at, c.company_name
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            ORDER BY j.created_at DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
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
        
    total_pages = max(1, (total_count + per_page - 1) // per_page)
        
    class CurrentUserMock:
        username = session.get("user_name", "Admin")
        
    return render_template(
        "admin_projects.html",
        projects=projects_list,
        current_user=CurrentUserMock(),
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        per_page=per_page
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



@app.route("/dashboard/ats/notify", methods=["POST"])
@login_required
def dashboard_ats_notify():
    if session.get("account_type") != "company":
        return jsonify({"success": False, "message": "Unauthorized access."}), 403
        
    data = request.get_json() or {}
    target_user_id = data.get("user_id")
    title = data.get("title", "").strip()
    message = data.get("message", "").strip()
    
    if not target_user_id or not title or not message:
        return jsonify({"success": False, "message": "Missing recipient, title, or message."}), 400
        
    conn = get_db()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM companies WHERE user_id = %s", (session["user_id"],))
        company = cursor.fetchone()
        if not company:
            return jsonify({"success": False, "message": "Company profile incomplete."}), 400
            
        cursor.execute("""
            SELECT a.id 
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE a.user_id = %s AND j.company_id = %s
        """, (target_user_id, company["id"]))
        
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Unauthorized: recipient has not applied to your opportunities."}), 403
            
        cursor.execute("""
            INSERT INTO notifications (user_id, title, message, link)
            VALUES (%s, %s, %s, %s)
        """, (target_user_id, title, message, "/dashboard/applications"))
        
    return jsonify({"success": True, "message": "Notification successfully sent to candidate."})


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
        
        # Dispatch in-app push notifications to targeted users
        if target == "all":
            cursor.execute("SELECT id FROM users WHERE is_banned = 0")
        elif target == "verified":
            cursor.execute("SELECT id FROM users WHERE verified = 1 AND is_banned = 0")
        elif target == "new":
            cursor.execute("SELECT id FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND is_banned = 0")
            
        target_users = cursor.fetchall()
        for u in target_users:
            cursor.execute("""
                INSERT INTO notifications (user_id, title, message, link)
                VALUES (%s, %s, %s, %s)
            """, (u["id"], f"Announcement: {title}", message, "/feed"))

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
