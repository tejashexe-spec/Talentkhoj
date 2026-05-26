
**Talent Khoj** is a Flask-based web application designed as a job discovery and talent matching platform for Nepal. The application provides a complete authentication system with user registration, login, email verification, password reset, and profile management features.

### Key Features Implemented:
- ✅ User Registration with validation
- ✅ Secure Login/Logout with session management
- ✅ Email Verification System
- ✅ Password Reset via Email
- ✅ User Profile Management (Name, Password, Avatar Upload)
- ✅ Responsive UI with modern design
- ✅ Flash Messages for user feedback
- ✅ Database integration with MySQL

---

## Project Structure

```
/workspace/
├── my_first_flask/
│   ├── __init__.py              # Package initialization
│   ├── app.py                   # Main Flask application entry point
│   ├── config.py                # Configuration and environment variables
│   │
│   ├── controllers/             # Business Logic Layer
│   │   ├── __init__.py
│   │   └── auth.py              # Authentication controller (login, register, logout)
│   │
│   ├── routes/                  # Route Definitions Layer
│   │   ├── __init__.py
│   │   └── auth.py              # Auth route blueprint
│   │
│   ├── model/                   # Data Access Layer
│   │   └── database.py          # Database connection and initialization
│   │
│   ├── services/                # External Services Layer
│   │   ├── __init__.py
│   │   └── email_service.py     # Email sending service (Resend API)
│   │
│   ├── static/                  # Static Assets
│   │   └── css/
│   │       └── style.css        # Main stylesheet
│   │
│   └── templates/               # HTML Templates (Jinja2)
│       ├── base.html            # Base template with navbar and footer
│       ├── home.html            # Homepage
│       ├── login.html           # Login page
│       ├── register.html        # Registration page
│       ├── profile.html         # User profile page
│       ├── verify_email.html    # Email verification request page
│       ├── verify_email_callback.html  # (Handled in app.py)
│       ├── reset_password.html  # Password reset request page
│       └── reset_password_confirm.html  # New password form
│
├── update_db.py                 # Database migration script
└── .env                         # Environment variables (not in repo)
```

---

## Architecture Overview

The application follows a **Layered Architecture** pattern with separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                      │
│  (Templates: base.html, login.html, register.html, etc.)    │
│  (Static Assets: CSS, Images)                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        ROUTE LAYER                           │
│  (routes/auth.py - URL routing and HTTP method handling)    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     CONTROLLER LAYER                         │
│  (controllers/auth.py - Business logic, validation, flow)   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                           │
│  (services/email_service.py - External API integrations)    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                       MODEL LAYER                            │
│  (model/database.py - Database connections and queries)     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                       DATABASE                               │
│  (MySQL - User data, tokens, sessions)                      │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow Example (Login):

1. **User** submits login form → `POST /login`
2. **Route Layer** captures request → `routes/auth.py`
3. **Controller Layer** processes logic → `controllers/auth.py`
   - Validates input
   - Queries database for user
   - Verifies password hash
4. **Model Layer** executes query → `database.py`
5. **Session** is created on success
6. **Response** redirects to homepage with flash message

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend Framework** | Flask  | Python web framework |
| **Database** | MySQL  | Relational database storage |
| **Database Driver** | PyMySQL | MySQL connector for Python |
| **Template Engine** | Jinja2 | Server-side HTML rendering |
| **Password Hashing** | Werkzeug | Secure password hashing (PBKDF2) |
| **Email Service** | Resend API | Transactional email delivery |
| **Session Storage** | Flask Sessions | Server-side session management |
| **CSS** | Custom CSS | Modern responsive styling |
| **Avatar Generation** | UI Avatars API | Default user avatars |

---

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    avatar VARCHAR(255) DEFAULT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    verification_token VARCHAR(255) DEFAULT NULL,
    verification_token_expires_at DATETIME DEFAULT NULL,
    reset_password_token VARCHAR(255) DEFAULT NULL,
    reset_password_token_expires_at DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Column Descriptions

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT | Primary key, auto-increment |
| `full_name` | VARCHAR(255) | User's full name |
| `email` | VARCHAR(255) | Unique email address (lowercase) |
| `password_hash` | VARCHAR(255) | Bcrypt/PBKDF2 hashed password |
| `avatar` | VARCHAR(255) | Path to uploaded profile picture |
| `email_verified` | BOOLEAN | Flag indicating email verification status |
| `verification_token` | VARCHAR(255) | Token for email verification |
| `verification_token_expires_at` | DATETIME | Expiration time for verification token (24 hours) |
| `reset_password_token` | VARCHAR(255) | Token for password reset |
| `reset_password_token_expires_at` | DATETIME | Expiration time for reset token (1 hour) |
| `created_at` | TIMESTAMP | Account creation timestamp |

---

## Authentication Flow

### 1. Registration Flow

```
User fills registration form
        ↓
Validate input (name, email, password match, length ≥ 8)
        ↓
Check if email already exists in database
        ↓
Hash password using Werkzeug (PBKDF2)
        ↓
Insert user into database
        ↓
Flash success message
        ↓
Redirect to login page
```


**Validation Rules:**
- Full name: Required, non-empty
- Email: Required, must contain "@"
- Password: Minimum 8 characters
- Confirm password: Must match password field

### 2. Login Flow

```
User enters email and password
        ↓
Query database for user by email
        ↓
Verify password hash using check_password_hash()
        ↓
If valid:
  - Store user_id, user_name, user_email, user_avatar in session
  - Redirect to homepage
If invalid:
  - Display error message
  - Stay on login page
```


**Session Data Stored:**
```python
session["user_id"] = user["id"]
session["user_name"] = user["full_name"]
session["user_email"] = user["email"]
session["user_avatar"] = user["avatar"]
```

### 3. Logout Flow

```
User clicks logout
        ↓
Clear entire session (session.clear())
        ↓
Flash info message
        ↓
Redirect to login page
```


---

## Email Verification System

### Overview
The email verification system ensures that users own the email addresses they register with. It uses secure tokens with expiration times.

### Flow Diagram

```
Request Verification
        ↓
User enters email on /verify-email
        ↓
Query database for user
        ↓
If user exists AND not verified:
  - Generate secure token (secrets.token_urlsafe(32))
  - Set expiration (24 hours from now)
  - Save token and expiry to database
  - Generate verification link with token
  - Send email via Resend API
  - Flash success message
  - Redirect to login
```

### Verification Callback

```
User clicks link: /verify-email/<token>
        ↓
Query database for token
        ↓
Check if token exists and not expired
        ↓
If valid:
  - Set email_verified = TRUE
  - Clear token and expiry
  - Flash success message
If expired/invalid:
  - Flash error message
        ↓
Redirect to login
```

### Email Template

```html
<p>Hi {user_name},</p>
<p>Please click the link below to verify your email address:</p>
<p><a href="{verification_link}">{verification_link}</a></p>
<p>This link will expire in 24 hours.</p>
```


### Security Features
- **Token Generation:** Uses `secrets.token_urlsafe(32)` for cryptographically secure tokens
- **Expiration:** Tokens expire after 24 hours
- **One-time Use:** Token is cleared after successful verification
- **Idempotent:** Already verified users get an info message

---

## Password Reset System

### Overview
Allows users to reset forgotten passwords via email with secure, time-limited tokens.

### Flow Diagram

#### Step 1: Request Reset

```
User enters email on /reset-password
        ↓
Query database for user
        ↓
If user exists:
  - Generate secure token (secrets.token_urlsafe(32))
  - Set expiration (1 hour from now)
  - Save token and expiry to database
  - Generate reset link with token
  - Send email via Resend API
  - Flash success message (even if user doesn't exist - security best practice)
        ↓
Redirect to login
```

#### Step 2: Reset Password

```
User clicks link: /reset-password/<token>
        ↓
GET request: Show password reset form
        ↓
POST request with new password:
  - Validate token exists and not expired
  - Validate new password (≥ 8 chars, matches confirmation)
  - Hash new password
  - Update password_hash in database
  - Clear reset token and expiry
  - Flash success message
        ↓
Redirect to login
```

### Email Template

```html
<p>Hi {user_name},</p>
<p>Please click the link below to reset your password:</p>
<p><a href="{reset_link}">{reset_link}</a></p>
<p>This link will expire in 1 hour.</p>
```


### Security Features
- **Short Expiration:** Reset tokens expire after 1 hour (shorter than verification)
- **Secure Token:** Cryptographically secure random tokens
- **No User Enumeration:** Same success message whether email exists or not
- **One-time Use:** Token cleared after successful reset

---

## User Profile Management

### Features

Users can manage their profile through `/profile` endpoint:

#### 1. Change Name
- Input: New full name
- Validation: Non-empty
- Updates: `users.full_name` and `session["user_name"]`

#### 2. Change Password
- Inputs: Current password, new password, confirm password
- Validations:
  - Current password must match stored hash
  - New password ≥ 8 characters
  - New password matches confirmation
- Updates: `users.password_hash`

#### 3. Upload Avatar
- Input: Image file (PNG, JPG, JPEG, GIF, WEBP)
- Processing:
  - Validates file extension
  - Generates unique filename: `user_{id}_{timestamp}.{ext}`
  - Saves to `/static/uploads/`
  - Updates: `users.avatar` and `session["user_avatar"]`

#### 4. Quick Links
- Verify Email button
- Logout button


### File Upload Security
- Only allowed image extensions
- Unique filenames prevent overwriting
- Files stored outside template directory

---

## Session Management

### Configuration
```python
app.secret_key = config.SECRET_KEY  # From environment variable
```

### Session Lifecycle

1. **Creation:** On successful login, user data stored in session
2. **Persistence:** Session persists across requests until:
   - User logs out (`session.clear()`)
   - Session expires (browser close, depending on configuration)
   - Server restarts (if using default filesystem sessions)
3. **Access:** Available in all templates via `session` context processor

### Context Processor
```python
@app.context_processor
def inject_session():
    return dict(session=session)
```

This makes `session` available in all templates without passing it explicitly.

### Protected Routes
Routes that require authentication check:
```python
if not session.get("user_id"):
    return redirect(url_for("login"))
```

---

## Frontend Templates

### Template Hierarchy

```
base.html (master template)
    ├── home.html
    ├── login.html
    ├── register.html
    ├── profile.html
    ├── verify_email.html
    ├── reset_password.html
    └── reset_password_confirm.html
```

### Base Template (`base.html`)

**Features:**
- Navbar with conditional rendering (logged in vs guest)
- Flash message display
- Profile dropdown menu
- Footer
- JavaScript for dropdown toggle

**Navbar Components:**
- Logo linking to homepage
- "Home" navigation link
- Conditional section:
  - **If logged in:** Profile picture + name dropdown with links to:
    - My Profile
    - Reset Password
    - Verify Email
    - Logout
  - **If guest:** "Sign In" button

### Template Variables

| Template | Variables |
|----------|-----------|
| `home.html` | `features` (list of feature cards) |
| `login.html` | `form_data`, `error` |
| `register.html` | `form_data`, `errors` (dict) |
| `profile.html` | `name_message`, `password_message`, `password_errors` |
| `verify_email.html` | None |
| `reset_password.html` | None |
| `reset_password_confirm.html` | `token` |

---

## Styling

### Design System

**Color Palette:**
- Primary Blue: `#2456ff`
- Background: `#f0ede8` (warm light gray)
- White: `#ffffff`
- Text Dark: `#1b1b1b`
- Text Medium: `#555555`
- Success Green: `#2d7a4f` / `#35a853`
- Error Red: `#e53e3e`
- Navy Footer: `#05154b`

**Typography:**
- Font Family: `'Segoe UI', sans-serif`
- Base Size: 14px
- Headings: 16px - 34px

**Components:**
- Rounded corners: `10px - 20px`
- Shadows: Soft shadows for depth
- Transitions: 0.2s ease for hover states

### Responsive Design
- Flexible layouts using Flexbox
- Mobile-friendly padding and margins
- Centered auth forms with max-width

**File:** `/static/css/style.css` (489 lines)

---

## Configuration & Environment Variables

### Config File (`config.py`)

```python
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "talent_khoj")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
```

### Required `.env` File

```bash
# Security
SECRET_KEY=your-super-secret-key-here-change-in-production

# Database
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=talent_khoj

# Email Service (Resend)
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxx

# OAuth (Future - Google Login)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

### Security Best Practices
1. Never commit `.env` file to version control
2. Use strong, unique `SECRET_KEY` in production
3. Restrict database user permissions
4. Use HTTPS in production

---

## API Endpoints Reference

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| GET | `/` | Homepage | No |
| GET/POST | `/register` | User registration | No |
| GET/POST | `/login` | User login | No |
| GET | `/logout` | User logout | Yes |
| GET/POST | `/verify-email` | Request email verification | No |
| GET | `/verify-email/<token>` | Email verification callback | No |
| GET/POST | `/reset-password` | Request password reset | No |
| GET/POST | `/reset-password/<token>` | Password reset form | No |
| GET/POST | `/profile` | User profile management | Yes |

### Request/Response Examples

#### POST /register
**Request Body (form-data):**
```
full_name: John Doe
email: john@example.com
password: securepass123
confirm_password: securepass123
```

**Success Response:**   
- Flash: "Registration successful. Please log in."
- Redirect: `/login`

#### POST /login
**Request Body (form-data):**
```
email: john@example.com
password: securepass123
```

**Success Response:**
- Session created
- Redirect: `/`

#### POST /profile (Change Password)
**Request Body (form-data):**
```
action: change_password
current_password: oldpass123
new_password: newpass456
confirm_password: newpass456
```

---

## Security Features

### Implemented Security Measures

1. **Password Hashing**
   - Algorithm: Werkzeug's PBKDF2-SHA256
   - Salt: Automatically generated per password
   - Never store plain text passwords

2. **SQL Injection Prevention**
   - Parameterized queries throughout
   - Example: `cursor.execute("SELECT * FROM users WHERE email = %s", (email,))`

3. **Session Security**
   - Server-side session storage
   - Secret key for signing cookies
   - Session cleared on logout

4. **Token Security**
   - Cryptographically secure tokens (`secrets.token_urlsafe(32)`)
   - Time-limited expiration
   - One-time use (cleared after use)

5. **Input Validation**
   - Client-side HTML5 validation
   - Server-side validation for all inputs
   - Email format validation
   - Password strength requirements

6. **XSS Prevention**
   - Jinja2 auto-escaping by default
   - All user input escaped in templates

7. **File Upload Security**
   - Whitelist of allowed extensions
   - Unique filenames
   - Stored outside web root where possible

### Future Security Enhancements
- [ ] Rate limiting on auth endpoints
- [ ] CSRF protection tokens
- [ ] Account lockout after failed attempts
- [ ] Two-factor authentication (2FA)
- [ ] OAuth2 integration (Google, GitHub)
- [ ] HTTPS enforcement
- [ ] Security headers (CSP, HSTS)

---

## Getting Started

### Prerequisites
- Python 3.8+
- MySQL 5.7+ or MariaDB
- pip (Python package manager)

### Installation Steps

1. **Clone/Navigate to Project**
   ```bash
   cd /workspace/my_first_flask
   ```

2. **Install Dependencies**
   ```bash
   pip install flask pymysql python-dotenv resend
   ```

3. **Create `.env` File**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Initialize Database**
   ```bash
   python update_db.py
   ```
   Or simply run the app - database tables are auto-created.

5. **Run Application**
   ```bash
   python app.py
   ```

   Or with Flask CLI:
   ```bash
   export FLASK_APP=app.py
   export FLASK_ENV=development
   flask run
   ```

6. **Access Application**
   Open browser to: `http://127.0.0.1:5000`

### Development Mode

The app runs in debug mode when started directly:
```python
if __name__ == "__main__":
    app.run(debug=True)
```

**Debug Features:**
- Auto-reload on code changes
- Interactive debugger in browser
- Detailed error pages

⚠️ **Never use debug mode in production!**

---

## Appendix A: File Inventory

### Python Files
| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 393 | Main application, all routes |
| `config.py` | 17 | Configuration management |
| `model/database.py` | 98 | Database connection & schema |
| `controllers/auth.py` | 76 | Auth business logic |
| `routes/auth.py` | 15 | Auth route definitions |
| `services/email_service.py` | 20 | Email sending service |
| `update_db.py` | ~60 | Database migration script |

### Templates
| File | Purpose |
|------|---------|
| `base.html` | Master template |
| `home.html` | Landing page |
| `login.html` | Login form |
| `register.html` | Registration form |
| `profile.html` | User profile |
| `verify_email.html` | Email verification request |
| `reset_password.html` | Password reset request |
| `reset_password_confirm.html` | New password form |

### Static Assets
| File | Purpose |
|------|---------|
| `static/css/style.css` | Main stylesheet (489 lines) |

---

## Appendix B: Common Issues & Solutions

### Issue: Database Connection Failed
**Solution:**
- Check MySQL service is running
- Verify `.env` credentials
- Ensure database user has CREATE privileges

### Issue: Emails Not Sending
**Solution:**
- Verify `RESEND_API_KEY` is set
- Check Resend dashboard for errors
- Ensure sender domain is verified in Resend

### Issue: Session Not Persisting
**Solution:**
- Ensure `SECRET_KEY` is set
- Check browser allows cookies
- Verify `session.modified = True` when updating

### Issue: Avatar Upload Fails
**Solution:**
- Create `/static/uploads/` directory
- Check write permissions
- Verify file size limits in server config

---

## Appendix C: Future Roadmap

### Planned Features
- [ ] Job posting and listing
- [ ] Resume upload and parsing
- [ ] Advanced search filters
- [ ] User dashboard with applications
- [ ] Employer accounts
- [ ] Email notifications for new jobs
- [ ] Social media integration
- [ ] Admin panel
- [ ] Analytics dashboard

### Technical Improvements
- [ ] Migrate to Flask Blueprints for better organization
- [ ] Add unit and integration tests
- [ ] Implement REST API
- [ ] Add Redis for caching
- [ ] Dockerize application
- [ ] CI/CD pipeline
- [ ] Database migrations with Alembic

---