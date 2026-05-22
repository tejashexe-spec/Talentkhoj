import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request, flash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

app.secret_key = "talent-khoj-secret-2025-sprint"


@app.context_processor
def inject_session():
    return dict(session=session)


@app.route("/")
def home():
    return render_template("home.html")


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

        # TODO: validate against database
        if email and password:
            session["user_id"] = 1
            session["user_name"] = email.split("@")[0].capitalize()
            session["user_email"] = email
            return redirect(url_for("home"))
        else:
            error = "Please enter your email and password."

    return render_template("login.html", form_data=form_data, error=error)


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
            # TODO: save user to database
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

    return render_template("register.html", form_data=form_data, errors=errors)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    
    # Pure frontend - no form processing
    return render_template("profile.html")


if __name__ == "__main__":
    app.run(debug=True)
