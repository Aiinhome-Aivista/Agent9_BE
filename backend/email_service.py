import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
import logging
from .config import get_settings

logger = logging.getLogger("aries.email")
settings = get_settings()

def _send_email_sync(to_email: str, subject: str, body_text: str, html_body: str = None) -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_USERNAME:
        logger.warning("SMTP configuration is missing. Skipping email send.")
        return False
        
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USERNAME
    msg["To"] = to_email
    msg["Subject"] = subject
    
    msg.attach(MIMEText(body_text, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))
    
    try:
        # Connect to SMTP server
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        # Send email
        server.send_message(msg)
        server.quit()
        logger.info(f"Successfully sent email to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

async def send_email_async(to_email: str, subject: str, body_text: str, html_body: str = None) -> bool:
    """Asynchronously send an email using smtplib wrapped in asyncio.to_thread."""
    if not to_email:
        logger.warning("No recipient email provided. Skipping email send.")
        return False
        
    return await asyncio.to_thread(_send_email_sync, to_email, subject, body_text, html_body)
