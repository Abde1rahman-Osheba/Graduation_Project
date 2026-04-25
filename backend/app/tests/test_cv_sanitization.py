"""Unit tests for the CV sanitization service.

These tests don't need any database — they validate the pure-Python
text cleaning rules required by `04_QDRANT_VECTOR_REQUIREMENTS.md`.
"""

from app.services.cv_sanitization_service import (
    detect_image_hints,
    detect_qr,
    sanitization_report,
    sanitize_cv_text,
)


def test_returns_empty_for_empty_input():
    assert sanitize_cv_text("") == ""
    assert sanitize_cv_text(None) == ""


def test_strips_data_uri_images():
    raw = "Hello\n<img src='data:image/png;base64,iVBORw0KGgo'>\nWorld"
    out = sanitize_cv_text(raw)
    assert "data:image" not in out
    assert "Hello" in out
    assert "World" in out


def test_strips_qr_hints():
    raw = "Skills: Python\nScan QR Code below to apply\nMore content"
    out = sanitize_cv_text(raw)
    assert "QR Code" not in out


def test_strips_logo_hints():
    raw = "Header text\n[company logo]\nMain body"
    out = sanitize_cv_text(raw)
    assert "logo" not in out.lower()
    assert "Main body" in out


def test_removes_repeated_headers_or_footers():
    header = "ACME Corporation Confidential"
    raw = "\n".join([header] * 5 + ["Real content goes here"])
    out = sanitize_cv_text(raw)
    assert header not in out
    assert "Real content" in out


def test_removes_page_numbers():
    raw = "Body 1\nPage 1 of 5\nBody 2\n3 of 5\nBody 3"
    out = sanitize_cv_text(raw)
    assert "Page 1 of 5" not in out
    assert "3 of 5" not in out
    assert "Body 1" in out
    assert "Body 3" in out


def test_collapses_excess_blank_lines():
    raw = "First\n\n\n\n\nSecond"
    out = sanitize_cv_text(raw)
    assert "\n\n\n" not in out


def test_detection_helpers():
    qr_text = "Please Scan QR Code to verify"
    img_text = "logo: ![logo here]"
    plain = "Just normal CV text"
    assert detect_qr(qr_text)
    assert not detect_qr(plain)
    assert detect_image_hints(img_text)
    assert not detect_image_hints(plain)


def test_sanitization_report_keys():
    report = sanitization_report("Scan QR Code\ndata:image/png;base64,AAAA")
    assert set(report.keys()) == {
        "had_images", "had_qr", "raw_length", "sanitized_length",
    }
    assert report["had_qr"] is True
    assert report["had_images"] is True
    assert report["sanitized_length"] <= report["raw_length"]
