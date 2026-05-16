from flask import Flask, render_template

app = Flask(__name__, template_folder=".")

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/contact")
def contact():
    return "This is contacts page"

@app.route("/about")
def about():
    return "This is about page."



if __name__ == "__main__":
    app.run(debug=True)