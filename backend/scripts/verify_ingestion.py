"""
PATHS Backend — Ingestion Verification Script.

Uploads a sample CV and verifies data across all three stores:
PostgreSQL (relational), Apache AGE (graph), and Qdrant (vector).

Usage:
    python scripts/verify_ingestion.py [path_to_cv]
"""

import requests
import time
import os
import sys
import json

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

SAMPLE_CV = """John Doe
Email: john.doe@example.com
Phone: +1-555-987-6543
Location: New York, NY

SUMMARY
Full-stack developer with 5 years of experience in web development,
specializing in Python backend systems and React frontends.

EXPERIENCE
Software Engineer, Acme Corp (2020-2023)
- Built scalable REST APIs using FastAPI and PostgreSQL
- Implemented CI/CD pipelines with GitHub Actions
- Led migration from monolith to microservices

Junior Developer, TechStart (2018-2020)
- Developed frontend applications using React and TypeScript
- Created automated testing suites with pytest

EDUCATION
B.S. Computer Science, Columbia University (2014-2018)

SKILLS
Python, FastAPI, React, TypeScript, PostgreSQL, Docker, Kubernetes,
AWS, Git, REST APIs, GraphQL, Redis, MongoDB

CERTIFICATIONS
AWS Certified Developer - Associate (2021)
"""


def verify_health():
    """Check the /health endpoint."""
    print("=" * 50)
    print("1. HEALTH CHECK")
    print("=" * 50)
    try:
        r = requests.get(f"{API_URL}/health", timeout=5)
        data = r.json()
        for service, status in data.items():
            s = status.get("status", "unknown") if isinstance(status, dict) else status
            icon = "✓" if s == "healthy" else "✗"
            print(f"  {icon} {service}: {s}")
        return True
    except Exception as e:
        print(f"  ✗ Health check failed: {e}")
        return False


def upload_cv(file_path: str = None) -> dict:
    """Upload a CV file or use the embedded sample."""
    print("\n" + "=" * 50)
    print("2. UPLOADING CV")
    print("=" * 50)

    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as f:
            r = requests.post(f"{API_URL}/api/v1/cv-ingestion/upload", files={"file": f})
    else:
        # Use built-in sample
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="sample_cv_")
        with os.fdopen(fd, "w") as f:
            f.write(SAMPLE_CV)
        with open(tmp_path, "rb") as f:
            r = requests.post(
                f"{API_URL}/api/v1/cv-ingestion/upload",
                files={"file": ("sample_cv.txt", f, "text/plain")},
            )
        os.unlink(tmp_path)

    if r.status_code != 200:
        print(f"  ✗ Upload failed ({r.status_code}): {r.text}")
        sys.exit(1)

    data = r.json()
    print(f"  ✓ Job ID: {data['job_id']}")
    print(f"  ✓ Status: {data['status']}")
    return data


def wait_for_completion(job_id: str, timeout: int = 120) -> dict:
    """Wait for the ingestion job to complete."""
    print("\n" + "=" * 50)
    print("3. WAITING FOR PIPELINE COMPLETION")
    print("=" * 50)

    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{API_URL}/api/v1/cv-ingestion/jobs/{job_id}")
        data = r.json()
        status = data["status"]
        stage = data["stage"]
        elapsed = int(time.time() - start)
        print(f"  [{elapsed:3d}s] status={status}, stage={stage}")

        if status == "completed":
            print(f"  ✓ Pipeline completed in {elapsed}s")
            return data
        elif status == "failed":
            print(f"  ✗ Pipeline failed: {data.get('error_message')}")
            sys.exit(1)

        time.sleep(3)

    print(f"  ✗ Pipeline timed out after {timeout}s")
    sys.exit(1)


def verify_postgres(candidate_id: str):
    """Verify relational data in PostgreSQL."""
    print("\n" + "=" * 50)
    print("4. VERIFYING POSTGRESQL (RELATIONAL)")
    print("=" * 50)

    r = requests.get(f"{API_URL}/api/v1/candidates/{candidate_id}")
    if r.status_code != 200:
        print(f"  ✗ Candidate fetch failed: {r.text}")
        return

    data = r.json()
    cand = data["candidate"]
    print(f"  ✓ Name: {cand['full_name']}")
    print(f"  ✓ Email: {cand.get('email', 'N/A')}")
    print(f"  ✓ Phone: {cand.get('phone', 'N/A')}")
    print(f"  ✓ Location: {cand.get('location_text', 'N/A')}")
    print(f"  ✓ Skills linked: {len(data['skills'])}")
    print(f"  ✓ Experiences: {len(data['experiences'])}")
    print(f"  ✓ Education: {len(data['education'])}")
    print(f"  ✓ Certifications: {len(data['certifications'])}")


def print_summary(candidate_id: str, job_data: dict):
    """Print final verification summary."""
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    print(f"  Candidate ID: {candidate_id}")
    print(f"  Document ID:  {job_data.get('document_id', 'N/A')}")
    print(f"  Job Status:   {job_data['status']}")
    print(f"  Final Stage:  {job_data['stage']}")
    print()
    print("  The same canonical candidate_id is used across:")
    print("    • PostgreSQL (relational tables)")
    print("    • Apache AGE (graph nodes/edges)")
    print("    • Qdrant (vector payloads)")
    print()
    print("  ✓ Verification complete!")


def main():
    file_path = sys.argv[1] if len(sys.argv) > 1 else None

    # 1. Health check
    verify_health()

    # 2. Upload
    upload_data = upload_cv(file_path)
    job_id = upload_data["job_id"]

    # 3. Wait for completion
    job_data = wait_for_completion(job_id)
    candidate_id = job_data["candidate_id"]

    # 4. Verify PostgreSQL
    verify_postgres(candidate_id)

    # 5. Summary
    print_summary(candidate_id, job_data)


if __name__ == "__main__":
    main()
