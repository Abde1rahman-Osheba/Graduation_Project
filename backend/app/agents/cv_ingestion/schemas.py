from typing import List, Optional
from pydantic import BaseModel, Field

class ScrapedSkill(BaseModel):
    name: str = Field(description="Name of the skill, technology, or tool.")
    category: Optional[str] = Field(None, description="Category of the skill (e.g., Programming Language, Framework, Database, Soft Skill)")

class ScrapedExperience(BaseModel):
    company_name: str = Field(description="Name of the company or organization.")
    title: str = Field(description="Job title or role.")
    start_date: Optional[str] = Field(None, description="Start date (try to parse into YYYY-MM if possible, else raw string)")
    end_date: Optional[str] = Field(None, description="End date (try to parse into YYYY-MM, or 'Present')")
    description: Optional[str] = Field(None, description="Detailed description of responsibilities and achievements.")

class ScrapedEducation(BaseModel):
    institution: str = Field(description="Name of the educational institution.")
    degree: Optional[str] = Field(None, description="Degree obtained (e.g., Bachelor of Science)")
    field_of_study: Optional[str] = Field(None, description="Major or field of study.")
    start_date: Optional[str] = Field(None, description="Start date of education")
    end_date: Optional[str] = Field(None, description="End date or graduation date")

class ScrapedCertification(BaseModel):
    name: str = Field(description="Name of the certification.")
    issuer: Optional[str] = Field(None, description="Issuing organization.")

class CandidateExtraction(BaseModel):
    full_name: str = Field(description="Candidate's full name.")
    email: Optional[str] = Field(None, description="Candidate's email address.")
    phone: Optional[str] = Field(None, description="Candidate's phone number.")
    location_text: Optional[str] = Field(None, description="Candidate's location (city, state, country).")
    summary: Optional[str] = Field(None, description="Professional summary or objective.")
    years_experience: Optional[int] = Field(None, description="Total years of professional experience, inferred from timeline.")
    skills: List[ScrapedSkill] = Field(default_factory=list, description="Extracted skills.")
    experiences: List[ScrapedExperience] = Field(default_factory=list, description="Extracted professional experiences.")
    education: List[ScrapedEducation] = Field(default_factory=list, description="Extracted educational background.")
    certifications: List[ScrapedCertification] = Field(default_factory=list, description="Extracted certifications.")
