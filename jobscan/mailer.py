import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import Config

log = logging.getLogger("jobscan")


def send(cfg: Config, subject: str, html: str, text: str) -> bool:
    if not cfg.email_to:
        log.error("mailer: no recipient configured (EMAIL_TO / config.email_to)")
        return False
    if not (cfg.smtp_user and cfg.smtp_pass):
        log.warning("mailer: SMTP_USER / SMTP_PASS not set - email not sent")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Job Scan <{cfg.email_from or cfg.smtp_user}>"
    msg["To"] = cfg.email_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        if cfg.smtp_port == 465:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port,
                                  context=ssl.create_default_context(), timeout=45) as s:
                s.login(cfg.smtp_user, cfg.smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=45) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(cfg.smtp_user, cfg.smtp_pass)
                s.send_message(msg)
        log.info("mailer: sent '%s' to %s", subject, cfg.email_to)
        return True
    except Exception as e:
        log.error("mailer: send failed: %s", str(e)[:200])
        return False
