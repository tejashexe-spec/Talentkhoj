from flask import render_template, request, redirect, url_for, flash, session


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
            # TODO: validate against database
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
                # TODO: save user to database
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("auth.login"))

        return render_template("register.html", form_data=form_data, errors=errors)

    def logout(self):
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("auth.login"))
