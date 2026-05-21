from flask import render_template, request, redirect, url_for, flash, session
from my_first_flask.model.database import Database
from werkzeug.security import generate_password_hash, check_password_hash

class AuthController:

    def login(self):
        if session.get("user_id"):
            return redirect(url_for("home"))

        form_data = {"email": ""}
        error = None

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            form_data = {"email": email}
            
            db = Database()
            query = "SELECT * FROM users WHERE email = %s"
            user = db.fetch_one(query, (email,))
            
            if user and check_password_hash(user['password'], password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                return redirect(url_for("home"))
            else:
                error = "Invalid email or password."

        return render_template("login.html", form_data=form_data, error=error)

    def register(self):
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
                db = Database()
                
                
                existing_user = db.fetch_one("SELECT id FROM users WHERE email = %s", (email,))
                if existing_user:
                    errors["email"] = "Email is already registered."
                else:
                    
                    hashed_password = generate_password_hash(password)
                    query = "INSERT INTO users (full_name, email, password) VALUES (%s, %s, %s)"
                    db.execute(query, (full_name, email, hashed_password))
                    
                    flash("Registration successful. Please log in.", "success")
                    return redirect(url_for("auth.login"))

        return render_template("register.html", form_data=form_data, errors=errors)

    def logout(self):
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("auth.login"))
