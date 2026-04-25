import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GRAPH_NAME = settings.age_graph_name if hasattr(settings, 'age_graph_name') else "paths_graph"

def init_graph(session: Session):
    """Ensure the graph is initialized."""
    session.execute(text("LOAD 'age';"))
    session.execute(text("SET search_path = ag_catalog, \"$user\", public;"))
    
    # Check if graph exists
    result = session.execute(
        text("SELECT * FROM ag_graph WHERE name = :graph_name;"),
        {"graph_name": GRAPH_NAME}
    ).fetchone()
    
    if not result:
        logger.info(f"Creating AGE graph '{GRAPH_NAME}'")
        session.execute(
            text("SELECT create_graph(:graph_name);"),
            {"graph_name": GRAPH_NAME}
        )
        session.commit()


def _cypher(session: Session, query: str, params: dict | None = None):
    # This is a basic wrapper. In real AGE usage with psychic/psycopg, 
    # parameter passing can be tricky depending on the driver.
    # Often, using cypher function in postgres requires string substitution 
    # or specific json casting if the driver doesn't support AGE types directly.
    # For safety, since this is for a prototype/spec constraint, 
    # we'll build the cypher string or use json parameters if psycopg handles them.
    
    # Using AGE with parameterized cypher usually requires:
    # SELECT * FROM cypher('graph_name', $$MATCH (n) WHERE n.id = $id RETURN n$$, '{"id": "value"}') as (v agtype);
    
    stmt = f"SELECT * FROM cypher('{GRAPH_NAME}', $${query}$$, :__cypher_params) as (result agtype);"
    
    # We pass __cypher_params as a JSON string to let AGE parse it.
    cypher_params = json.dumps(params) if params else "{}"
    return session.execute(text(stmt), {"__cypher_params": cypher_params})


def project_candidate(session: Session, candidate_id: str, payload: dict):
    """Upsert Candidate node."""
    query = """
    MERGE (c:Candidate {candidate_id: $id})
    SET c.full_name = $full_name, c.email = $email, c.years_experience = $years_xp
    RETURN c
    """
    params = {
        "id": candidate_id,
        "full_name": payload.get("full_name"),
        "email": payload.get("email"),
        "years_xp": payload.get("years_experience")
    }
    _cypher(session, query, params)


def project_skill(session: Session, candidate_id: str, skill_id: str, skill_name: str, score: int | None = None):
    """Upsert Skill and link to Candidate."""
    normalized_name = skill_name.strip().lower() if skill_name else ""
    query = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    MERGE (s:Skill {name: $skill_name})
    SET s.normalized_name = $skill_name
    MERGE (c)-[r:HAS_SKILL]->(s)
    SET r.proficiency_score = $score
    RETURN r
    """
    params = {
        "candidate_id": candidate_id,
        "skill_name": normalized_name,
        "score": score
    }
    _cypher(session, query, params)


def project_company(session: Session, candidate_id: str, company: str, title: str):
    """Upsert Company and work edge."""
    query = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    MERGE (comp:Company {name: $company_name})
    MERGE (c)-[r:WORKED_AT {title: $title}]->(comp)
    RETURN r
    """
    params = {
        "candidate_id": candidate_id,
        "company_name": company,
        "title": title
    }
    _cypher(session, query, params)


def project_education(session: Session, candidate_id: str, institution: str, degree: str):
    """"Upsert Education and link."""
    query = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    MERGE (edu:Education {institution: $institution})
    SET edu.degree = $degree
    MERGE (c)-[r:STUDIED_AT]->(edu)
    RETURN r
    """
    params = {
        "candidate_id": candidate_id,
        "institution": institution,
        "degree": degree
    }
    _cypher(session, query, params)


def project_certification(session: Session, candidate_id: str, name: str, issuer: str):
    """Upsert Certification and link."""
    query = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    MERGE (cert:Certification {name: $name})
    SET cert.issuer = $issuer
    MERGE (c)-[r:HAS_CERTIFICATION]->(cert)
    RETURN r
    """
    params = {
        "candidate_id": candidate_id,
        "name": name,
        "issuer": issuer
    }
    _cypher(session, query, params)


def project_document(session: Session, candidate_id: str, document_id: str):
    """Upsert Document node."""
    query = """
    MERGE (c:Candidate {candidate_id: $candidate_id})
    MERGE (d:Document {document_id: $document_id})
    SET d.type = 'cv'
    MERGE (d)-[r:DESCRIBES]->(c)
    RETURN r
    """
    params = {
        "candidate_id": candidate_id,
        "document_id": document_id
    }
    _cypher(session, query, params)


def project_job(session: Session, job_id: str, title: str, company_name: str,
                seniority_level: str | None = None, experience_level: str | None = None):
    """Upsert Job node in the graph."""
    query = """
    MERGE (j:Job {job_id: $job_id})
    SET j.title = $title, j.company_name = $company_name,
        j.seniority_level = $seniority_level, j.experience_level = $experience_level
    RETURN j
    """
    params = {
        "job_id": job_id,
        "title": title,
        "company_name": company_name,
        "seniority_level": seniority_level,
        "experience_level": experience_level,
    }
    _cypher(session, query, params)


def project_job_skill(session: Session, job_id: str, skill_name: str):
    """Create REQUIRES_SKILL edge between a Job and a Skill node."""
    normalized_name = skill_name.strip().lower() if skill_name else ""
    query = """
    MERGE (j:Job {job_id: $job_id})
    MERGE (s:Skill {name: $skill_name})
    MERGE (j)-[r:REQUIRES_SKILL]->(s)
    RETURN r
    """
    params = {
        "job_id": job_id,
        "skill_name": normalized_name,
    }
    _cypher(session, query, params)


def project_job_company(session: Session, job_id: str, company_name: str):
    """Create POSTED_BY edge between a Job and a Company node."""
    query = """
    MERGE (j:Job {job_id: $job_id})
    MERGE (comp:Company {name: $company_name})
    MERGE (j)-[r:POSTED_BY]->(comp)
    RETURN r
    """
    params = {
        "job_id": job_id,
        "company_name": company_name,
    }
    _cypher(session, query, params)
