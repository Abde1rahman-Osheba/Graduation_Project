"""
Path B — validate CSV, SSRF-safe CV download, LangGraph CV ingestion, dedup,
and unified candidate sync.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import tempfile
import uuid
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.cv_ingestion.graph import ingestion_app
from app.agents.cv_ingestion.state import CVIngestionState
from app.core.config import get_settings
from app.db.models.candidate import Candidate
from app.db.models.candidate_extras import CandidateLink
from app.db.repositories import organization_matching_repo
from app.services.candidate_sync_service import sync_candidate_full
from app.services.scoring.relevance_filter_service import _normalize

logger = logging.getLogger(__name__)
settings = get_settings()

_ALLOWED_CT = {
    x.strip().lower()
    for x in settings.org_cv_allowed_content_types.replace("\n", ",").split(",")
    if x.strip()
}


def _is_private_ip(ip: str) -> bool:
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
        )
    except ValueError:
        return True


def _host_ips(hostname: str) -> list[str]:
    import socket

    infos = socket.getaddrinfo(hostname, None)
    return [x[4][0] for x in infos if x[4] and x[4][0]]


def is_safe_http_url_for_cv(url: str) -> tuple[bool, str]:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False, "only_http_or_https"
    m = re.match(r"^https?://([^/?:]+)", u, re.I)
    if not m:
        return False, "bad_url"
    host = m.group(1).lower()
    if host in ("localhost",) or host.endswith(".local") or host == "0.0.0.0":
        return False, "blocked_host"
    if not settings.org_cv_block_private_networks:
        return True, "ok"
    try:
        for ip in _host_ips(host):
            if _is_private_ip(ip):
                return False, f"private_ip:{ip}"
    except Exception:  # noqa: BLE001
        return False, "dns_failed"
    return True, "ok"


def _suffix_from_url(url: str) -> str:
    lower = url.lower().split("?", 1)[0]
    for ext in (".pdf", ".docx", ".doc", ".txt"):
        if lower.endswith(ext):
            return ext
    return ".bin"


def _download_cv(url: str) -> tuple[str | None, str | None]:
    ok, reason = is_safe_http_url_for_cv(url)
    if not ok:
        return None, f"ssrf_check_failed:{reason}"
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=float(settings.org_cv_download_timeout_seconds),
        ) as client:
            with client.stream("GET", url) as r:
                if r.status_code >= 400:
                    return None, f"http_{r.status_code}"
                ct = (r.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if ct and _ALLOWED_CT and ct not in _ALLOWED_CT:
                    return None, f"bad_content_type:{ct}"
                cl = r.headers.get("content-length")
                max_b = int(settings.org_cv_max_file_size_mb) * 1024 * 1024
                if cl and cl.isdigit() and int(cl) > max_b:
                    return None, "file_too_large"
                data = b""
                for chunk in r.iter_bytes(65536):
                    data += chunk
                    if len(data) > max_b:
                        return None, "file_too_large"
        if not data:
            return None, "empty_body"
    except Exception as exc:  # noqa: BLE001
        return None, f"download_error:{str(exc)[:200]}"
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=_suffix_from_url(url),
    ) as f:
        f.write(data)
        return f.name, None


def _find_duplicate_candidate(
    db: Session,
    *,
    email: str | None,
    linkedin: str | None,
    github: str | None,
) -> UUID | None:
    if email and email.strip():
        c = db.execute(
            select(Candidate).where(Candidate.email == email.strip())
        ).scalar_one_or_none()
        if c:
            return c.id
    for needle in (linkedin, github):
        if not needle or len(needle) < 8:
            continue
        n = _normalize(needle)[:60]
        row = db.execute(
            select(Candidate.id)
            .join(CandidateLink, CandidateLink.candidate_id == Candidate.id)
            .where(CandidateLink.url.ilike(f"%{n}%"))
            .limit(1)
        ).scalar_one_or_none()
        if row:
            return row
    return None


def _ingest_file(temp_path: str, *, existing_candidate_id: UUID | None) -> tuple[UUID | None, str | None]:
    job_id = str(uuid.uuid4())
    st: CVIngestionState = {
        "job_id": job_id,
        "candidate_id": str(existing_candidate_id) if existing_candidate_id else None,
        "document_id": None,
        "file_path": temp_path,
        "raw_text": None,
        "structured_candidate": None,
        "normalized_candidate": None,
        "chunks": None,
        "embeddings": None,
        "errors": [],
        "status": "running",
        "stage": "started",
    }
    final = ingestion_app.invoke(st)
    if final.get("status") == "failed":
        return None, (final.get("errors") and "\n".join(final["errors"])) or "ingestion_failed"
    cid = final.get("candidate_id")
    if not cid:
        return None, "no_candidate_id"
    return UUID(str(cid)), None


def import_candidates_from_csv(
    db: Session,
    *,
    organization_id: UUID,
    matching_run_id: UUID,
    import_id: UUID,
    file_bytes: bytes,
    _file_name: str,
) -> dict[str, Any]:
    _ = organization_id
    result: dict[str, Any] = {
        "total_rows": 0, "valid_rows": 0, "imported_candidates": 0,
        "updated_candidates": 0, "failed_rows": 0, "candidate_ids": [],
    }
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = {x.strip().lower() for x in (reader.fieldnames or [])}
    if "cv_url" not in fields:
        organization_matching_repo.log_candidate_import_error(
            db,
            {
                "import_id": import_id,
                "matching_run_id": matching_run_id,
                "row_number": None,
                "cv_url": None,
                "error_type": "InvalidCsv",
                "error_message": "CSV must include cv_url column",
                "raw_row": None,
            },
        )
        db.commit()
        return result
    fmap = {k.strip().lower(): k for k in (reader.fieldnames or [])}

    for i, row in enumerate(reader, start=2):
        if i - 2 >= int(settings.org_csv_max_rows):
            break
        result["total_rows"] += 1
        cv_url = (row.get(fmap.get("cv_url", "cv_url")) or "").strip()
        if not cv_url:
            result["failed_rows"] += 1
            organization_matching_repo.log_candidate_import_error(
                db,
                {
                    "import_id": import_id, "matching_run_id": matching_run_id,
                    "row_number": i, "cv_url": "", "error_type": "MissingCvUrl",
                    "error_message": "empty cv_url", "raw_row": dict(row),
                },
            )
            db.commit()
            continue
        result["valid_rows"] += 1
        em = (row.get(fmap.get("candidate_email", "candidate_email")) or "").strip() or None
        li = (row.get(fmap.get("linkedin_url", "linkedin_url")) or "").strip() or None
        gh = (row.get(fmap.get("github_url", "github_url")) or "").strip() or None
        dup = _find_duplicate_candidate(db, email=em, linkedin=li, github=gh)

        path, err = _download_cv(cv_url)
        if err or not path:
            result["failed_rows"] += 1
            organization_matching_repo.log_candidate_import_error(
                db,
                {
                    "import_id": import_id, "matching_run_id": matching_run_id,
                    "row_number": i, "cv_url": cv_url, "error_type": "Download",
                    "error_message": err, "raw_row": dict(row),
                },
            )
            db.commit()
            continue
        try:
            was_dup = dup is not None
            new_id, perr = _ingest_file(path, existing_candidate_id=dup)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if not new_id:
            result["failed_rows"] += 1
            organization_matching_repo.log_candidate_import_error(
                db,
                {
                    "import_id": import_id, "matching_run_id": matching_run_id,
                    "row_number": i, "cv_url": cv_url, "error_type": "Ingestion",
                    "error_message": perr, "raw_row": dict(row),
                },
            )
            db.commit()
            continue
        try:
            sync_candidate_full(db, new_id, force_vector=True)
        except Exception:  # noqa: BLE001
            logger.exception("post-import sync for %s", new_id)
        if was_dup:
            result["updated_candidates"] += 1
        else:
            result["imported_candidates"] += 1
        result["candidate_ids"].append(str(new_id))
    return result
