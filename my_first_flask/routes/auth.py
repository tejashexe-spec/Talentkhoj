from flask import Blueprint
from my_first_flask.controllers.auth import AuthController


class AuthRoutes:
    def __init__(self):
        self.bp = Blueprint("auth", __name__)
        self.controller = AuthController()

    def register(self):
        self.bp.route("/login", methods=["GET", "POST"])(self.controller.login)
        self.bp.route("/register", methods=["GET", "POST"])(self.controller.register)
        self.bp.route("/logout")(self.controller.logout)
        return self.bp
