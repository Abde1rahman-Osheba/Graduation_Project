"""
PATHS Backend — Deterministic skill dictionary.

Maps lowercase aliases to canonical skill names. Used by the job
normalizer (and reusable elsewhere) to extract a controlled set of
skills from free-text scraped descriptions before we ask an LLM.

Keep entries simple and well-known to avoid false positives. Anything
exotic / domain-specific should be added here intentionally.
"""

from __future__ import annotations

import re
from typing import Iterable

# Canonical name -> aliases (lowercase, no extra punctuation)
SKILL_DICTIONARY: dict[str, list[str]] = {
    "Python": ["python", "py3", "python3"],
    "JavaScript": ["javascript", "js", "node.js", "nodejs", "node js"],
    "TypeScript": ["typescript", "ts"],
    "Java": ["java"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["golang", "go"],
    "Rust": ["rust"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "Apache Kafka": ["kafka", "apache kafka"],
    "RabbitMQ": ["rabbitmq"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "Linux": ["linux"],
    "Git": ["git"],
    "GitHub": ["github"],
    "GitLab": ["gitlab"],
    "CI/CD": ["ci/cd", "ci cd", "continuous integration"],
    "FastAPI": ["fastapi"],
    "Django": ["django"],
    "Flask": ["flask"],
    "React": ["react", "react.js", "reactjs"],
    "Next.js": ["next.js", "nextjs"],
    "Vue.js": ["vue.js", "vuejs", "vue"],
    "Angular": ["angular", "angular.js", "angularjs"],
    "Node.js": ["node.js", "nodejs"],
    "Express": ["express", "express.js", "expressjs"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    ".NET": [".net", "dotnet", "asp.net"],
    "Laravel": ["laravel"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "restful", "rest api"],
    "gRPC": ["grpc"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "TensorFlow": ["tensorflow", "tf"],
    "PyTorch": ["pytorch", "torch"],
    "Scikit-Learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "LLM": ["llm", "large language model", "large language models"],
    "LangChain": ["langchain"],
    "LangGraph": ["langgraph"],
    "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "OpenAI": ["openai", "open ai"],
    "Hugging Face": ["hugging face", "huggingface"],
    "Apache Spark": ["apache spark", "spark"],
    "Hadoop": ["hadoop"],
    "Airflow": ["airflow"],
    "dbt": ["dbt"],
    "Snowflake": ["snowflake"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Excel": ["excel", "microsoft excel"],
    "Figma": ["figma"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3"],
    "Tailwind CSS": ["tailwind", "tailwindcss", "tailwind css"],
    "Bootstrap": ["bootstrap"],
    "Sass": ["sass", "scss"],
    "iOS": ["ios"],
    "Android": ["android"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Flutter": ["flutter"],
    "React Native": ["react native"],
    "Selenium": ["selenium"],
    "Playwright": ["playwright"],
    "Cypress": ["cypress"],
    "Jest": ["jest"],
    "Pytest": ["pytest"],
    "Agile": ["agile", "scrum"],
    "Jira": ["jira"],
    "Confluence": ["confluence"],
    "Project Management": ["project management"],
    "Communication": ["communication"],
    "Leadership": ["leadership"],
    "Salesforce": ["salesforce"],
    "SAP": ["sap"],
    "Cybersecurity": ["cybersecurity", "cyber security"],
    "DevOps": ["devops"],
    "MLOps": ["mlops"],
}


# Pre-build a flat alias → canonical map and a regex to find any alias
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in SKILL_DICTIONARY.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical


def _alias_pattern() -> re.Pattern[str]:
    # Sort aliases longest-first so "react native" wins over "react"
    aliases = sorted(_ALIAS_TO_CANONICAL.keys(), key=len, reverse=True)
    escaped = [re.escape(a) for a in aliases]
    # Word-boundary style match. We use lookarounds because some aliases
    # contain non-word characters like ".", "/", "+", "#".
    return re.compile(
        r"(?<![\w])(?:" + "|".join(escaped) + r")(?![\w])",
        flags=re.IGNORECASE,
    )


_ALIAS_REGEX = _alias_pattern()


def normalize_skill(raw: str) -> str | None:
    """Map a raw skill string to the canonical name, or None if unknown."""
    if not raw:
        return None
    return _ALIAS_TO_CANONICAL.get(raw.strip().lower())


def extract_skills_from_text(text: str | Iterable[str]) -> list[str]:
    """Extract canonical skills mentioned anywhere in the input text.

    Returns the skills in first-seen order (deduplicated).
    """
    if not text:
        return []
    if not isinstance(text, str):
        text = " \n ".join(str(t) for t in text if t)
    seen: set[str] = set()
    out: list[str] = []
    for match in _ALIAS_REGEX.finditer(text):
        canonical = _ALIAS_TO_CANONICAL.get(match.group(0).lower())
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def normalize_skill_list(skills: Iterable[str]) -> list[str]:
    """Map an iterable of raw skill names to canonical, deduped order."""
    out: list[str] = []
    seen: set[str] = set()
    for s in skills:
        canonical = normalize_skill(s)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out
