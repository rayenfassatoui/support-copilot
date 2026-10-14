from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl
from typing import Literal

from fastapi import Request

from app.config import Settings
from app.errors import DomainError


@dataclass(frozen=True)
class OutboundMail:
    recipient: str
    subject: str
    body: str
    message_id: str


@dataclass(frozen=True)
class DeliveryOutcome:
    status: Literal["sent", "failed", "unknown"]
    error: str | None = None


class SMTPMailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def require_configured(self) -> None:
        if not self.settings.smtp_host:
            raise DomainError("mail_not_configured")

    def send(self, mail: OutboundMail) -> DeliveryOutcome:
        self.require_configured()
        message = EmailMessage()
        message["From"] = str(self.settings.smtp_from)
        message["To"] = mail.recipient
        message["Subject"] = mail.subject
        message["Message-ID"] = mail.message_id
        message.set_content(mail.body)
        connection = None
        try:
            if self.settings.smtp_security == "tls":
                connection = smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port,
                                              timeout=self.settings.smtp_timeout, context=ssl.create_default_context())
            else:
                connection = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout)
            connection.ehlo()
            if self.settings.smtp_security == "starttls":
                connection.starttls(context=ssl.create_default_context())
                connection.ehlo()
            if self.settings.smtp_username:
                connection.login(self.settings.smtp_username, self.settings.smtp_password.get_secret_value())
        except (OSError, smtplib.SMTPException):
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            return DeliveryOutcome("failed", "smtp_connection_failed")
        try:
            refused = connection.send_message(message, from_addr=str(self.settings.smtp_from), to_addrs=[mail.recipient])
            return DeliveryOutcome("failed", "smtp_rejected") if refused else DeliveryOutcome("sent")
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPResponseException):
            return DeliveryOutcome("failed", "smtp_rejected")
        except (OSError, smtplib.SMTPException):
            # DATA may already have been accepted: automatic retry could duplicate delivery.
            return DeliveryOutcome("unknown", "smtp_delivery_unconfirmed")
        finally:
            try:
                connection.close()
            except OSError:
                pass


def get_mailer(request: Request) -> SMTPMailer:
    return request.app.state.mailer
