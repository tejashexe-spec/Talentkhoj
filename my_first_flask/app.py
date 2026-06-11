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


# ─── HOME ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/feed", methods=["GET"])
@login_required
def get_feed():
    user_id = session.get("user_id", 0)
    page = int(request.args.get("page", 1))
    per_page = 10
    offset = (page - 1) * per_page

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("ajax") == "1":
        conn = get_db()
        SQL_QUERY = """
            SELECT p.id, p.content, p.image_path, p.created_at,
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
@login_required
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
        
    return render_template("user_profile.html", user=user, reviews=reviews, avg_rating=avg_rating, review_count=review_count)


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
        
    return render_template("company_profile.html", company=company, reviews=reviews, avg_rating=avg_rating, review_count=review_count)


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
    return render_template("dashboard_saved.html", bookmarks=bookmarks)



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


if __name__ == "__main__":
    app.run(debug=True)
