import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request, flash
from my_first_flask import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, "templates"),
            static_folder=os.path.join(BASE_DIR, "static"))

app.secret_key = config.SECRET_KEY


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


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    name_message = None
    password_message = None
    password_errors = []

    if request.method == "POST":
        action = request.form.get("action")

        if action == "change_name":
            full_name = request.form.get("full_name", "").strip()
            if not full_name:
                name_message = "Name cannot be empty."
            else:
                session["user_name"] = full_name
                session.modified = True
                # TODO: update full_name in users table WHERE id = session['user_id']
                name_message = "Name updated successfully."

        elif action == "change_password":
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            if len(new_password) < 8:
                password_errors.append("New password must be at least 8 characters.")
            if new_password != confirm_password:
                password_errors.append("Passwords do not match.")
            if not password_errors:
                # TODO: hash new_password and update password_hash in users table WHERE id = session['user_id']
                password_message = "Password updated successfully."

    return render_template("profile.html",
        name_message=name_message,
        password_message=password_message,
        password_errors=password_errors
    )


if __name__ == "__main__":
    app.run(debug=True)
