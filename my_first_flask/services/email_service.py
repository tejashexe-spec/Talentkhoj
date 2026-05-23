import resend
from my_first_flask import config

class EmailService:
    @staticmethod
    def send_email(to: str, subject: str, html: str):
        resend.api_key = config.RESEND_API_KEY
        
        try:
            response = resend.Emails.send({
                "from": "onboarding@resend.dev",
                "to": to,
                "subject": subject,
                "html": html
            })
            return response
        except Exception as e:
            print(f"Failed to send email: {e}")
            return None
