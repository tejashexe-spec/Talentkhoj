import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template
from my_first_flask.routes.auth import AuthRoutes


def create_app():
    app = Flask(__name__)
    app.secret_key = "key"

    @app.route("/")
    def home():
        return render_template("home.html")

    auth_routes = AuthRoutes()
    app.register_blueprint(auth_routes.register())

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
