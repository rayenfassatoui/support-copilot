from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
import socket
from threading import Thread

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.errors import DomainError
from app.knowledge_import import MAX_BYTES, download, extract, public_target


POLICY = "AcmeCloud fictional policy: billing disputes require a human review before any refund is promised."


def pdf_bytes(text=None, *, pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.set_data(f"BT /F1 12 Tf 40 700 Td ({escaped}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-only-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_upload_indexes_extracted_page_text_and_can_be_read_back(client):
    response = client.post("/api/knowledge/import/file", data={"title": "Synthetic PDF policy"}, files={"file": ("policy.pdf", pdf_bytes(POLICY), "application/pdf")})
    assert response.status_code == 201, response.text
    document = response.json()
    assert "[Page 1]" in document["content"] and POLICY in document["content"]
    assert client.get(f"/api/knowledge/{document['id']}").json()["content"] == document["content"]


@pytest.mark.parametrize("options,code", [({"encrypted": True, "text": POLICY}, "knowledge_import_encrypted_pdf"), ({}, "knowledge_import_no_text"), ({"text": "x", "pages": 10}, "knowledge_import_no_text"), ({"pages": 201}, "knowledge_import_too_large")])
def test_pdf_rejects_encryption_scans_and_page_overflow(options, code):
    with pytest.raises(DomainError) as raised:
        extract(pdf_bytes(**options), "application/pdf")
    assert raised.value.code == code


def test_upload_validation_prevents_blank_titles_and_oversized_or_nontext_sources(client, provider):
    assert client.post("/api/knowledge/import/file", data={"title": "   "}, files={"file": ("policy.txt", POLICY.encode())}).status_code == 422
    unsupported = client.post("/api/knowledge/import/file", data={"title": "Image"}, files={"file": ("image.png", b"image bytes")})
    assert unsupported.json()["detail"]["code"] == "knowledge_import_unsupported"
    oversized = client.post("/api/knowledge/import/file", data={"title": "Too large"}, files={"file": ("large.txt", b"x" * (MAX_BYTES + 1))})
    assert oversized.status_code == 413
    assert client.get("/api/knowledge").json() == [] and provider.calls == []


def test_html_import_removes_noncontent_without_running_or_retaining_scripts():
    text = extract(f"<html><head><title>Hidden title</title><style>secret style</style></head><body><h1>Billing</h1><p>{POLICY}</p><script>secret script</script></body></html>".encode(), "text/html; charset=utf-8")
    assert POLICY in text and "Billing" in text
    assert "Hidden title" not in text and "secret" not in text and "<script>" not in text


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "::ffff:127.0.0.1", "2002:7f00:1::", "224.0.0.1"])
def test_url_import_rejects_private_and_embedded_private_addresses(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))])
    with pytest.raises(DomainError) as raised:
        public_target("http://public.example.com/policy")
    assert raised.value.code == "knowledge_import_unsafe_url"


def test_one_private_dns_answer_rejects_the_entire_target(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80)) for address in ("8.8.8.8", "127.0.0.1")])
    with pytest.raises(DomainError) as raised:
        public_target("http://public.example.com/")
    assert raised.value.code == "knowledge_import_unsafe_url"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:password@example.com/", "http://example.com:8080/", "https://example.com/\r\nHeader: value"])
def test_url_import_rejects_unsafe_schemes_ports_credentials_and_controls(url):
    with pytest.raises(DomainError) as raised:
        public_target(url)
    assert raised.value.code == "knowledge_import_unsafe_url"


def test_redirect_cannot_reach_private_network_and_connection_uses_validated_ip(monkeypatch):
    requests, connections = [], []

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.headers["Host"], self.path))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/private")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Redirect)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def resolve(host, port, **kwargs):
        address = "8.8.8.8" if host == "public.example.com" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    def connect(address, timeout):
        connections.append(address)
        assert address == ("8.8.8.8", 80)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(server.server_address)
        return sock

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "create_connection", connect)
    try:
        with pytest.raises(DomainError) as raised:
            download("http://public.example.com/policy")
        assert raised.value.code == "knowledge_import_unsafe_url"
        assert connections == [("8.8.8.8", 80)]
        assert requests == [("public.example.com", "/policy")]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
