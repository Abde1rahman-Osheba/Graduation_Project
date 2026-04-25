"""
PATHS Backend — CV sanitization service.

Sanitizes raw CV text before it is fed to the embedding model. The spec
explicitly requires removing image / QR / logo / header / footer noise so
that vectors are built from useful semantic content only.

This module does **text-level** sanitization only — at this layer the
upstream PDF parser has already returned plain text, so we focus on
artifacts that commonly leak into extracted text (data URIs, base64
blobs, repeated headers/footers, page numbers, etc.).
"""

from __future__ import annotations

import re
from collections import Counter

# ── Regex patterns for noise removal ─────────────────────────────────────

_RE_DATA_URI = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_RE_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}")
_RE_QR_HINT = re.compile(
    r"(QR\s*Code|Scan\s+(?:to|me)|qrcode|qr_code)", re.IGNORECASE,
)
_RE_LOGO_HINT = re.compile(
    r"\b(?:company\s+logo|brand\s+logo|logo)\b", re.IGNORECASE,
)
_RE_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d+\s*(?:/|of)\s*\d+\s*$", re.IGNORECASE)
_RE_BARE_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,3}\s*$", re.IGNORECASE)
_RE_FORMFEED = re.compile(r"\f")
_RE_MULTI_BLANK = re.compile(r"\n{3,}")
_RE_NON_PRINTABLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_RE_TRAILING_WS = re.compile(r"[ \t]+\n")


def _strip_repeated_lines(lines: list[str], min_repetitions: int = 3) -> list[str]:
    """Remove lines that repeat across many pages (typical headers/footers).

    A line is considered a header/footer if it's short (<= 80 chars) and
    occurs at least `min_repetitions` times in the document.
    """
    if not lines:
        return lines
    counts = Counter(line.strip() for line in lines if line.strip())
    repeated = {
        line
        for line, c in counts.items()
        if c >= min_repetitions and len(line) <= 80
    }
    if not repeated:
        return lines
    return [line for line in lines if line.strip() not in repeated]


def detect_qr(raw_text: str) -> bool:
    return bool(_RE_QR_HINT.search(raw_text or ""))


def detect_image_hints(raw_text: str) -> bool:
    return bool(
        _RE_DATA_URI.search(raw_text or "") or _RE_LOGO_HINT.search(raw_text or "")
    )


def sanitize_cv_text(raw_text: str | None) -> str:
    """Return a sanitized version of the CV text safe for embedding.

    Removes:
      * image data URIs and obvious base64 blobs
      * QR-code text hints / "scan to view"
      * "logo" markers
      * page numbers
      * repeated header/footer lines
      * non-printable control characters
      * excessive blank lines
    """
    if not raw_text:
        return ""

    text = raw_text

    # Replace form-feed (PDF page boundary) with newline
    text = _RE_FORMFEED.sub("\n", text)

    # Drop image/qr/logo noise
    text = _RE_DATA_URI.sub(" ", text)
    text = _RE_BASE64_BLOB.sub(" ", text)
    text = _RE_QR_HINT.sub(" ", text)
    text = _RE_LOGO_HINT.sub(" ", text)
    text = _RE_NON_PRINTABLE.sub(" ", text)

    # Line-level cleanup
    lines = text.split("\n")
    keep: list[str] = []
    for line in lines:
        if _RE_PAGE_NUMBER.match(line):
            continue
        if _RE_BARE_PAGE_NUMBER.match(line) and len(line.strip()) <= 4:
            continue
        keep.append(line.rstrip())

    keep = _strip_repeated_lines(keep)

    text = "\n".join(keep)
    text = _RE_TRAILING_WS.sub("\n", text)
    text = _RE_MULTI_BLANK.sub("\n\n", text)
    return text.strip()


def sanitization_report(raw_text: str | None) -> dict[str, bool | int]:
    raw = raw_text or ""
    return {
        "had_images": detect_image_hints(raw),
        "had_qr": detect_qr(raw),
        "raw_length": len(raw),
        "sanitized_length": len(sanitize_cv_text(raw)),
    }
