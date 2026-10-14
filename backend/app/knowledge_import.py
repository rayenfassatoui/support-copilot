from io import BytesIO
import http.client
import ipaddress
import multiprocessing
import re
import socket
import ssl
import sys
from urllib.parse import quote, urljoin, urlsplit

from app.errors import DomainError
from app.text import HTMLText

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARACTERS = 500000


def public_target(url: str) -> tuple[str, str, int, str]:
    try:
        if any(ord(char) < 32 or ord(char) == 127 for char in url):
            raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port not in {80, 443}:
            raise ValueError()
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError()
        for _, _, _, _, endpoint in addresses:
            address = ipaddress.ip_address(endpoint[0])
            embedded = getattr(address, "ipv4_mapped", None) or getattr(address, "sixtofour", None)
            if not address.is_global or address.is_multicast or (embedded is not None and not embedded.is_global) or getattr(address, "teredo", None):
                raise ValueError()
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parsed.query:
            path += "?" + quote(parsed.query, safe="%=&/?@!$'()*+,;:-._~")
        return host, addresses[0][4][0], port, path
    except (ValueError, UnicodeError, OSError):
        raise DomainError("knowledge_import_unsafe_url") from None


def download(url: str) -> tuple[bytes, str, str]:
    for _ in range(6):
        host, address, port, path = public_target(url)
        secure = urlsplit(url).scheme == "https"
        context = ssl.create_default_context()
        connection = http.client.HTTPSConnection(host, port, timeout=5, context=context) if secure else http.client.HTTPConnection(host, port, timeout=5)
        sock = None
        try:
            # The connected address is the validated numeric IP; TLS still verifies the original hostname.
            sock = socket.create_connection((address, port), timeout=5)
            connection.sock = context.wrap_socket(sock, server_hostname=host) if secure else sock
            connection.request("GET", path, headers={"Accept": "text/html,text/plain,text/markdown,application/pdf", "Accept-Encoding": "identity", "User-Agent": "SupportCopilot-Knowledge/1.0"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise DomainError("knowledge_import_unavailable")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise DomainError("knowledge_import_unavailable")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise DomainError("knowledge_import_unsupported")
            size = response.getheader("Content-Length")
            if size and (not size.isdigit() or int(size) > MAX_BYTES):
                raise DomainError("knowledge_import_too_large")
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise DomainError("knowledge_import_too_large")
            return data, response.getheader("Content-Type", "text/plain"), url
        except (OSError, http.client.HTTPException):
            raise DomainError("knowledge_import_unavailable") from None
        finally:
            connection.close()
            if sock is not None:
                sock.close()
    raise DomainError("knowledge_import_unsafe_url")


def extract(data: bytes, media_type: str) -> str:
    if len(data) > MAX_BYTES:
        raise DomainError("knowledge_import_too_large")
    content_type = media_type.split(";", 1)[0].strip().lower()
    if content_type == "application/pdf" or data.startswith(b"%PDF-"):
        from pypdf import PdfReader
        try:
            if not data.startswith(b"%PDF-"):
                raise DomainError("knowledge_import_invalid_pdf")
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise DomainError("knowledge_import_encrypted_pdf")
            if len(reader.pages) > 200:
                raise DomainError("knowledge_import_too_large")
            pages, size = [], 0
            for number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                size += len(text.strip())
                if size > MAX_CHARACTERS:
                    raise DomainError("knowledge_import_too_large")
                if text.strip():
                    pages.append(f"[Page {number}]\n{text}")
            if size < 50:
                raise DomainError("knowledge_import_no_text")
            content = "\n\n".join(pages)
        except DomainError:
            raise
        except Exception:
            raise DomainError("knowledge_import_invalid_pdf") from None
    elif content_type in {"text/plain", "text/markdown", "text/html", "application/xhtml+xml"}:
        charset = re.search(r"charset\s*=\s*[\"']?([\w-]+)", media_type, re.I)
        encoding = charset.group(1).lower() if charset else "utf-8-sig"
        if encoding not in {"utf-8", "utf-8-sig", "iso-8859-1", "windows-1252"}:
            raise DomainError("knowledge_import_invalid_text")
        try:
            content = data.decode(encoding)
        except UnicodeError:
            raise DomainError("knowledge_import_invalid_text") from None
        if content_type in {"text/html", "application/xhtml+xml"}:
            parser = HTMLText(MAX_CHARACTERS)
            try:
                parser.feed(content)
            except OverflowError:
                raise DomainError("knowledge_import_too_large") from None
            content = parser.text()
    else:
        raise DomainError("knowledge_import_unsupported")
    content = content.replace("\r\n", "\n").strip()
    if "\x00" in content:
        raise DomainError("knowledge_import_invalid_text")
    if len(content) < 50:
        raise DomainError("knowledge_import_no_text")
    if len(content) > MAX_CHARACTERS:
        raise DomainError("knowledge_import_too_large")
    return content


def import_worker(pipe, source: bytes | str, media_type: str | None):
    try:
        if sys.platform == "linux":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        if isinstance(source, str):
            data, content_type, final_url = download(source)
        else:
            data, content_type, final_url = source, media_type or "application/octet-stream", None
        pipe.send({"content": extract(data, content_type), "url": final_url})
    except DomainError as error:
        pipe.send({"error": error.code})
    except Exception:
        pipe.send({"error": "knowledge_import_unavailable"})
    finally:
        pipe.close()


def import_source(source: bytes | str, media_type: str | None = None) -> tuple[str, str | None]:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=import_worker, args=(sender, source, media_type), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(30):
            raise DomainError("knowledge_import_timeout")
        try:
            result = receiver.recv()
        except EOFError:
            raise DomainError("knowledge_import_unavailable") from None
        if "error" in result:
            raise DomainError(result["error"])
        return result["content"], result["url"]
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
        process.close()
