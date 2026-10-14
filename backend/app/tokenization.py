"""Pinned Liquid tokenizer; download only through the explicit build/development CLI."""
from functools import lru_cache
import hashlib
from pathlib import Path

import httpx
from tokenizers import Tokenizer

TOKENIZER_REVISION = "bf1712f052040a2af193db0fe1e98c6f0df2da0f"
TOKENIZER_BLOB_SHA1 = "9c4e858fd7847c8046826120f07b89ade34ed9bd"
TOKENIZER_PATH = Path(__file__).resolve().parent / "assets" / "liquid-tokenizer.json"
EMBEDDING_TOKEN_LIMIT = 512


@lru_cache(maxsize=1)
def get_tokenizer() -> Tokenizer:
    tokenizer = Tokenizer.from_file(str(TOKENIZER_PATH))
    # Model assets may declare a truncation policy. Preflight must never truncate.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


def token_count(text: str) -> int:
    return len(get_tokenizer().encode(text, add_special_tokens=True).ids)


def prewarm() -> None:
    url = f"https://huggingface.co/LiquidAI/LFM2.5-Embedding-350M/resolve/{TOKENIZER_REVISION}/tokenizer.json"
    with httpx.Client(timeout=45.0, follow_redirects=True) as http:
        response = http.get(url)
        response.raise_for_status()
        data = response.content
    # Verify the immutable repository blob, not a mutable 'main' tokenizer.
    blob = f"blob {len(data)}\0".encode() + data
    if hashlib.sha1(blob).hexdigest() != TOKENIZER_BLOB_SHA1:
        raise RuntimeError("Liquid tokenizer integrity check failed.")
    TOKENIZER_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENIZER_PATH.write_bytes(data)
    get_tokenizer.cache_clear()
    assert token_count("document: AcmeCloud fictional demo policy") < EMBEDDING_TOKEN_LIMIT
    print(f"Liquid tokenizer ready: revision {TOKENIZER_REVISION}; offline runtime validation.")


if __name__ == "__main__":
    prewarm()
