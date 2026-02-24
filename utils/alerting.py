import smtplib
import ssl
import requests
from email.message import EmailMessage
from core.logger import setup_logger

logger = setup_logger(__name__)

class AlertManager:
    """Manages outgoing alerts via Email and Slack"""
    
    @staticmethod
    def send_email(subject: str, body: str, to_email: str, config: dict):
        """Send a secure email alert"""
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = config.get('smtp_from', 'alert@aws-monitor.local')
        msg['To'] = to_email
        
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(config['smtp_server'], config.get('smtp_port', 587)) as server:
                server.starttls(context=context)
                if config.get('smtp_user') and config.get('smtp_password'):
                    server.login(config['smtp_user'], config['smtp_password'])
                server.send_message(msg)
            logger.info(f"Alert email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    @staticmethod
    def send_slack(webhook_url: str, message: str):
        """Send a Slack notification via Webhook"""
        try:
            response = requests.post(webhook_url, json={"text": message}, timeout=10)
            if response.status_code != 200:
                logger.error(f"Slack alert failed: {response.text}")
                return False
            logger.info("Slack alert sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
