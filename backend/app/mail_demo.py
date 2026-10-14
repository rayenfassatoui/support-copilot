"""Inject synthetic email into the local GreenMail inbox, never an external server."""

import argparse
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", default="Demo: help with a duplicate subscription charge")
    parser.add_argument("--body", default="Hello support, my fictional AcmeCloud subscription shows two charges this month. Please explain how I can request a review. This is synthetic demo data.")
    parser.add_argument("--in-reply-to", help="An existing Message-ID to exercise conversation threading")
    args = parser.parse_args()
    settings = load_settings()
    if settings.mail_delivery_mode != "mailpit" or settings.imap_host not in {"mailbox", "localhost", "127.0.0.1", "::1"} or settings.imap_port != 3143:
        parser.error("This command only targets the local GreenMail demo on IMAP port 3143.")
    message = EmailMessage()
    message["From"] = "Demo Customer <customer@example.com>"
    message["To"] = "support@example.com"
    message["Subject"] = args.subject
    message["Message-ID"] = make_msgid(domain="demo.example.com")
    message["Date"] = formatdate(localtime=False)
    if args.in_reply_to:
        message["In-Reply-To"] = args.in_reply_to
        message["References"] = args.in_reply_to
    message.set_content(args.body)
    with smtplib.SMTP(settings.imap_host, 3025, timeout=15) as smtp:
        smtp.send_message(message)
    print(f"Synthetic email accepted by local GreenMail. Message-ID: {message['Message-ID']}")
    print("Open Support mailbox → Sync now, then open the imported ticket. No external email was sent.")


if __name__ == "__main__":
    main()
