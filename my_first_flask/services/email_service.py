import json
from flask import current_app
from flask_mail import Message
from my_first_flask import config
from my_first_flask.model.database import Database

class EmailService:
    _db = None
    
    @staticmethod
    def _get_db():
        if EmailService._db is None:
            EmailService._db = Database()
        return EmailService._db
    
    @staticmethod
    def _log_email(from_email: str, to_email: str, subject: str, html: str, status: str, error_message: str = None, resend_response: dict = None):
        try:
            conn = EmailService._get_db().get_connection()
            with conn.cursor() as cursor:
                response_json = json.dumps(resend_response) if resend_response else None
                cursor.execute("""
                    INSERT INTO mail_logs 
                    (from_email, to_email, subject, html_content, status, error_message, resend_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (from_email, to_email, subject, html, status, error_message, response_json))
        except Exception as log_error:
            print(f"Failed to log email: {log_error}")
    
    @staticmethod
    def send_email(to: str, subject: str, html: str):
        from_email = config.MAIL_USERNAME
        
        print(f"Attempting to send email to {to} with subject: {subject} via Google SMTP")
        
        # Resolve the Mail instance from current_app or fall back to importing from app.py
        mail = None
        try:
            if current_app:
                mail = current_app.extensions.get('mail')
        except RuntimeError:
            pass
            
        if not mail:
            try:
                from my_first_flask.app import mail
            except ImportError as imp_err:
                print(f"Could not import mail instance: {imp_err}")
        
        if not mail:
            error_msg = "Mail client is not initialized."
            print(error_msg)
            EmailService._log_email(from_email, to, subject, html, "failed", error_message=error_msg)
            return None
            
        try:
            msg = Message(
                subject=subject,
                sender=from_email,
                recipients=[to],
                html=html
            )
            
            mail.send(msg)
            print("Email sent successfully via Google SMTP!")
            
            response = {
                "status": "sent",
                "provider": "google_smtp"
            }
            EmailService._log_email(from_email, to, subject, html, "success", resend_response=response)
            return response
            
        except Exception as e:
            error_msg = str(e)
            print(f"Failed to send email via Google SMTP: {error_msg}")
            EmailService._log_email(from_email, to, subject, html, "failed", error_message=error_msg)
            return None
