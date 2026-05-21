import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, session, redirect, url_for, request
from my_first_flask.routes.auth import AuthRoutes


def create_app():
    app = Flask(__name__)
    app.secret_key = "key"

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/profile")
    def profile():
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return render_template("profile.html")

    @app.route("/profile/edit", methods=["GET", "POST"])
    def profile_edit():
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))

        message = None

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            if full_name:
                session["user_name"] = full_name
                session.modified = True
                message = "Profile updated successfully."

        return render_template("profile_edit.html", message=message)

    auth_routes = AuthRoutes()
    app.register_blueprint(auth_routes.register())

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
