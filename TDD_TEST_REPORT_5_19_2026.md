# TDD Testing Report

Date: May 19, 2026

Project: Flask Login and Registration App

## Introduction

This report is based on the Flask code given for the group project. My task was to check the main parts of the program and see whether the app can run properly, whether the routes are correct, and whether the register and login logic make sense.

Since this is a testing report, I focused on the expected behavior of the app and the problems found in the code.

## What I Checked

I checked these parts of the project:

- app setup
- route definitions
- template rendering
- register form validation
- login form logic
- MySQL database connection setup

## Test Environment

Project folder:

`C:\Users\tejas\Documents\Codex\2026-05-19\from-flask-import-flask-render-template`

Things I was able to do:

- review the code
- check the local repaired file for Python syntax errors

Things I could not fully run in this environment:

- Flask was not installed in the bundled runtime
- PyMySQL was not installed in the bundled runtime
- a live MySQL database was not connected

Because of this, some tests are based on code review and some are marked as blocked.

## Test Cases

| Test Case | Expected Result | Actual Result | Status |
|---|---|---|---|
| App should start without syntax errors | Program should run correctly | The original code has an incomplete `if __name__ == "__main__":` block and indentation problems | Fail |
| Flask app should be created only once | One app object should keep all config values | The code creates `app` two times, so the second one overrides the first one | Fail |
| Templates should load from the `templates` folder | `home.html`, `login.html`, and `register.html` should load correctly | The second app uses `template_folder="."`, which is not the intended folder | Fail |
| `/register` route should work correctly | Register page should open and handle form submission | Register logic is mostly present, but the full app cannot run because of earlier code problems | Blocked |
| `/login` route should work correctly | Login page should open and check email/password | The `login()` function returns too early, so the login checking code does not run | Fail |
| `/contact` route should work | Contact page should return a response | Extra misindented code is placed inside `contact()` | Fail |
| `/about` route should work | About page should return a response | The first return works, but there is unreachable code after it | Fail |
| Registration should reject invalid input | Invalid form data should show errors | Validation code exists, but full execution was not completed here | Blocked |
| Registration should reject duplicate email | Existing email should not be saved again | Duplicate-email check exists, but full execution was not completed here | Blocked |
| Login should accept valid credentials | Correct email and password should pass | Full login test was not run because Flask and database packages were unavailable | Blocked |
| Login should reject wrong credentials | Wrong email or password should fail | Full login test was not run because Flask and database packages were unavailable | Blocked |
| Repaired local `app.py` should compile | Cleaned version should pass syntax check | The repaired local file passed `py_compile` | Pass |

## Main Problems Found

### 1. App object is created twice

The code first creates the app with the correct template folder and config, but later it creates another `Flask` app again. This can remove the earlier settings.

### 2. `/login` route is used in two places

The route `/login` is connected once above `register()` and again in the real `login()` function. This makes the route setup confusing and incorrect.

### 3. Login logic does not run

Inside the `login()` function, `return render_template("login.html")` comes before the actual checking code. Because of that, the rest of the login logic never executes.

### 4. Indentation problem in `contact()`

There is extra code under the `contact()` route that does not belong there. This causes a syntax or structure problem in the file.

### 5. Main block is incomplete

The line:

`if __name__ == "__main__":`

is incomplete in the original code. This means the program cannot start properly in that form.

### 6. Unreachable code in `about()`

The `about()` function returns one value, and then there is another return statement after it. The second one will never be used.

## Final Result

From testing and code review, I found that the original code is not ready to run as it is. The main reason is that it has route conflicts, unreachable code, indentation issues, and an incomplete main block.

The repaired local version is in a better state and passed Python syntax compilation, but full Flask and database testing was not completed in this environment because the required packages were missing.

## Conclusion

Based on this testing task, the app still needs fixing before proper feature testing can be completed. The first priority should be:

1. remove the duplicate Flask app creation
2. fix the `/login` route setup
3. remove unreachable code
4. fix indentation and complete the main block
5. install dependencies and test with a real MySQL connection

After these fixes, proper TDD-style testing can be done for register, login, and route behavior.
