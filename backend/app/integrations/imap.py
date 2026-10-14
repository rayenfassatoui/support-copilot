from contextlib import contextmanager
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
import hashlib
import imaplib
import re
import ssl

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.config import Settings
from app.text import HTMLText

MAX_MAIL_BYTES = 2_000_000
MESSAGE_ID = re.compile(r"<[^<>\x00-\x20\x7f@]+@[^<>\x00-\x20\x7f@]+>")
EMAIL = TypeAdapter(EmailStr)


class MailInputError(Exception):
    def __init__(self, code: str, *, ignored: bool = False):
        self.code = code
        self.ignored = ignored
        super().__init__(code)


@dataclass(frozen=True)
class IncomingMail:
    sender: str
    subject: str
    body: str
    message_id: str
    references: list[str]
    in_reply_to: str | None
    warning: str | None = None


def mailbox_key(settings: Settings) -> str:
    identity = f"{settings.imap_host.lower()}:{settings.imap_port}\n{settings.imap_username}\n{settings.imap_folder}"
    return hashlib.sha256(identity.encode()).hexdigest()


def message_ids(value: str) -> list[str]:
    ids = list(dict.fromkeys(item for item in MESSAGE_ID.findall(value) if len(item) <= 998))
    return ids if len(ids) <= 30 else [ids[0], *ids[-29:]]


def parse_mail(raw: bytes, settings: Settings) -> IncomingMail:
    if len(raw) > MAX_MAIL_BYTES:
        raise MailInputError("message_too_large")
    try:
        mail = BytesParser(policy=policy.default).parsebytes(raw)
        if mail.defects:
            raise MailInputError("malformed_message")
        addresses = getaddresses(mail.get_all("From", []))
        if len(addresses) != 1:
            raise MailInputError("invalid_sender")
        sender = str(EMAIL.validate_python(addresses[0][1])).lower()
        if sender == str(settings.smtp_from).lower():
            raise MailInputError("self_message", ignored=True)
        if str(mail.get("Auto-Submitted", "no")).lower() != "no" or str(mail.get("Precedence", "")).lower() in {"bulk", "list", "junk"} or mail.get_content_type() == "multipart/report":
            raise MailInputError("automated_message", ignored=True)
        ids = message_ids(str(mail.get("Message-ID", "")))
        if len(mail.get_all("Message-ID", [])) != 1 or len(ids) != 1:
            raise MailInputError("missing_or_invalid_message_id")
        subject = " ".join(str(mail.get("Subject", "")).split()) or "Email without subject"
        if len(subject) > 200:
            raise MailInputError("subject_too_long")
        if "\x00" in subject:
            raise MailInputError("invalid_subject")
        parts = list(mail.walk())
        if len(parts) > 100:
            raise MailInputError("too_many_mime_parts")
        body_part = mail.get_body(preferencelist=("plain", "html"))
        if body_part is None or body_part.get_content_type() not in {"text/plain", "text/html"}:
            raise MailInputError("no_text_body")
        body = body_part.get_content(errors="strict")
        if body_part.defects or not isinstance(body, str) or "\x00" in body:
            raise MailInputError("invalid_text_body")
        if body_part.get_content_type() == "text/html":
            parser = HTMLText(10000)
            parser.feed(body)
            body = parser.text()
        body = body.replace("\r\n", "\n").strip()
        if not body or len(body) > 10000:
            raise MailInputError("empty_or_oversized_body")
        reply_ids = message_ids(str(mail.get("In-Reply-To", "")))
        references = message_ids(str(mail.get("References", "")))
        references = list(dict.fromkeys([*references, *reply_ids]))
        if len(references) > 30:
            references = [references[0], *references[-29:]]
        warning = "attachments_kept_in_mailbox" if any(part.get_content_disposition() == "attachment" for part in parts) else None
        return IncomingMail(sender, subject, body, ids[0], references, reply_ids[-1] if reply_ids else None, warning)
    except MailInputError:
        raise
    except (ValueError, LookupError, UnicodeError, ValidationError, OverflowError):
        raise MailInputError("malformed_message") from None


@contextmanager
def connect(settings: Settings):
    connection = None
    try:
        if settings.imap_security == "tls":
            connection = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=ssl.create_default_context(), timeout=settings.imap_timeout)
        else:
            connection = imaplib.IMAP4(settings.imap_host, settings.imap_port, timeout=settings.imap_timeout)
            if settings.imap_security == "starttls":
                connection.starttls(ssl_context=ssl.create_default_context())
        connection.login(settings.imap_username, settings.imap_password.get_secret_value())
        status, _ = connection.select('"' + settings.imap_folder.replace('\\', '\\\\').replace('"', '\\"') + '"', readonly=True)
        if status != "OK":
            raise imaplib.IMAP4.error("mailbox_select_failed")
        validity = connection.response("UIDVALIDITY")[1]
        if not validity or not validity[0] or int(validity[0]) <= 0:
            raise imaplib.IMAP4.error("invalid_uid_validity")
        yield connection, int(validity[0])
    finally:
        if connection is not None:
            try:
                connection.logout()
            except (OSError, imaplib.IMAP4.error):
                connection.shutdown()


def pending_uids(connection, last_uid: int, limit: int) -> list[int]:
    status, data = connection.uid("search", None, "UID", f"{last_uid + 1}:*")
    if status != "OK":
        raise imaplib.IMAP4.error("mailbox_search_failed")
    return sorted(int(value) for value in data[0].split() if int(value) > last_uid)[:limit]


def fetch_mail(connection, uid: int) -> bytes:
    status, metadata = connection.uid("fetch", str(uid), "(RFC822.SIZE)")
    if status != "OK":
        raise imaplib.IMAP4.error("mailbox_fetch_failed")
    size = re.search(rb"RFC822.SIZE\s+(\d+)", b" ".join(item for item in metadata if isinstance(item, bytes)))
    if not size:
        raise MailInputError("message_removed")
    if int(size.group(1)) > MAX_MAIL_BYTES:
        raise MailInputError("message_too_large")
    status, data = connection.uid("fetch", str(uid), f"(BODY.PEEK[]<0.{MAX_MAIL_BYTES + 1}>)")
    if status != "OK":
        raise imaplib.IMAP4.error("mailbox_fetch_failed")
    bodies = [item[1] for item in data if isinstance(item, tuple) and isinstance(item[1], bytes)]
    if len(bodies) != 1:
        raise MailInputError("message_removed")
    return bodies[0]
