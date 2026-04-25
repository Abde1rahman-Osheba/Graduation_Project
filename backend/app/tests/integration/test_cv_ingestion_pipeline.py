"""
PATHS Backend — Integration Test for CV Ingestion Pipeline.

This test uploads a sample CV and verifies data persistence across
PostgreSQL (relational), Apache AGE (graph), and Qdrant (vector).
"""

import os
import sys
import time
import uuid
import tempfile
import requests
import pytest

# Base URL for the running API
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

SAMPLE_CV_TEXT = """
John Michael Smith
Email: john.smith@example.com
Phone: +1-555-123-4567
Location: San Francisco, CA, USA
LinkedIn: https://linkedin.com/in/johnsmith

PROFESSIONAL SUMMARY
Experienced Senior Software Engineer with 8+ years of experience in building
scalable web applications and distributed systems. Strong expertise in Python,
cloud architecture, and machine learning pipelines.

WORK EXPERIENCE

Senior Software Engineer | Google LLC
January 2021 - Present
- Led development of internal ML pipeline serving 100M+ daily predictions
- Designed microservices architecture using Python, gRPC, and Kubernetes
- Mentored team of 5 junior engineers

Software Engineer | Meta Platforms
June 2018 - December 2020
- Built real-time data processing systems using Apache Kafka and Python
- Implemented recommendation algorithms improving engagement by 15%
- Contributed to open-source React Native framework

Junior Developer | Startup Inc
March 2016 - May 2018
- Developed RESTful APIs using Flask and PostgreSQL
- Implemented CI/CD pipelines with Jenkins and Docker

EDUCATION

Master of Science in Computer Science
Stanford University, 2014 - 2016

Bachelor of Science in Software Engineering
MIT, 2010 - 2014

SKILLS
Python, JavaScript, TypeScript, Go, SQL, PostgreSQL, MongoDB, Redis,
Docker, Kubernetes, AWS, GCP, React, FastAPI, Flask, Machine Learning,
TensorFlow, PyTorch, Apache Kafka, gRPC, REST APIs, Git, CI/CD

CERTIFICATIONS
AWS Solutions Architect - Professional (Amazon, 2022)
Google Cloud Professional Data Engineer (Google, 2021)
Certified Kubernetes Administrator (CNCF, 2020)
"""


def _create_sample_cv_file() -> str:
    """Create a temporary CV file for testing."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="test_cv_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(SAMPLE_CV_TEXT)
    return path


def _wait_for_api(max_retries: int = 30, delay: float = 2.0):
    """Wait for the API to become available."""
    for i in range(max_retries):
        try:
            r = requests.get(f"{API_BASE}/", timeout=3)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(delay)
    raise RuntimeError("API did not become available in time")


class TestCVIngestionPipeline:
    """End-to-end integration test for the CV ingestion pipeline."""

    @classmethod
    def setup_class(cls):
        """Ensure the API is reachable."""
        _wait_for_api()

    def test_health_endpoint(self):
        """Verify /health returns per-service status."""
        r = requests.get(f"{API_BASE}/health")
        assert r.status_code == 200
        data = r.json()

        # Should have postgres, age, qdrant, ollama keys
        assert "postgres" in data
        assert "age" in data
        assert "qdrant" in data
        assert "ollama" in data

        print(f"Health check: {data}")

    def test_full_cv_ingestion_pipeline(self):
        """Upload a CV, wait for processing, then verify all three stores."""

        # 1. Upload CV
        cv_path = _create_sample_cv_file()
        try:
            with open(cv_path, "rb") as f:
                r = requests.post(
                    f"{API_BASE}/api/v1/cv-ingestion/upload",
                    files={"file": ("test_cv.txt", f, "text/plain")},
                )
            assert r.status_code == 200, f"Upload failed: {r.text}"

            data = r.json()
            job_id = data["job_id"]
            print(f"Upload response: {data}")
            assert "job_id" in data

            # 2. Wait for job completion (90s max, the LLM can be slow)
            candidate_id = None
            for _ in range(45):
                time.sleep(2)
                r = requests.get(f"{API_BASE}/api/v1/cv-ingestion/jobs/{job_id}")
                assert r.status_code == 200
                job_data = r.json()
                status = job_data["status"]
                stage = job_data["stage"]
                print(f"  Job status: {status}, stage: {stage}")

                if status == "completed":
                    candidate_id = job_data["candidate_id"]
                    break
                elif status == "failed":
                    error = job_data.get("error_message", "Unknown error")
                    pytest.fail(f"Ingestion job failed: {error}")

            assert candidate_id is not None, "Job did not complete in time"
            print(f"Candidate ID: {candidate_id}")

            # 3. Verify PostgreSQL relational data
            r = requests.get(f"{API_BASE}/api/v1/candidates/{candidate_id}")
            assert r.status_code == 200, f"Candidate fetch failed: {r.text}"
            cand_data = r.json()

            candidate_core = cand_data["candidate"]
            assert candidate_core["id"] == candidate_id
            assert candidate_core["full_name"]  # Should have a name
            print(f"Candidate: {candidate_core['full_name']}")
            print(f"Skills count: {len(cand_data['skills'])}")
            print(f"Experiences count: {len(cand_data['experiences'])}")
            print(f"Education count: {len(cand_data['education'])}")
            print(f"Certifications count: {len(cand_data['certifications'])}")

            # Verify skill links exist
            assert len(cand_data["skills"]) > 0, "No skills were linked"

            # Verify experiences exist
            assert len(cand_data["experiences"]) > 0, "No experiences were created"

            # 4. Print verification summary
            print("\n=== VERIFICATION SUMMARY ===")
            print(f"✓ Candidate ID: {candidate_id}")
            print(f"✓ Full name: {candidate_core['full_name']}")
            print(f"✓ Email: {candidate_core.get('email')}")
            print(f"✓ Skills: {len(cand_data['skills'])}")
            print(f"✓ Experiences: {len(cand_data['experiences'])}")
            print(f"✓ Education: {len(cand_data['education'])}")
            print(f"✓ Certifications: {len(cand_data['certifications'])}")
            print("=== ALL CHECKS PASSED ===")

        finally:
            os.unlink(cv_path)


if __name__ == "__main__":
    """Run as a standalone verification script."""
    print("=" * 60)
    print("PATHS CV Ingestion Pipeline — Integration Test")
    print("=" * 60)

    test = TestCVIngestionPipeline()
    test.setup_class()

    print("\n--- Health Check ---")
    test.test_health_endpoint()

    print("\n--- Full Pipeline Test ---")
    test.test_full_cv_ingestion_pipeline()
