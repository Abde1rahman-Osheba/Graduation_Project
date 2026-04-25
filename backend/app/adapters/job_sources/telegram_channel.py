"""
PATHS Backend — Telegram Channel Job Aggregator Adapter.
"""
import httpx
import logging
from bs4 import BeautifulSoup
from app.adapters.job_sources.base import BaseJobSourceAdapter

logger = logging.getLogger(__name__)

class TelegramChannelAdapter(BaseJobSourceAdapter):
    name = "telegram_channel"
    source_type = "telegram_channel"

    def __init__(self, max_pages: int = 20):
        self.max_pages = max_pages
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}

    async def discover(self, query: dict | None = None) -> list[str]:
        if query and "urls" in query:
            return query["urls"][:self.max_pages]
        return []

    async def fetch(self, target: str) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0, headers=self.headers) as client:
                response = await client.get(target)
                response.raise_for_status()
                return {
                    "source_url": target,
                    "html": response.text,
                    "status_code": response.status_code,
                    "target_id": target,
                }
        except Exception as e:
            logger.error(f"Failed to fetch {target}: {str(e)}")
            return {
                "source_url": target,
                "html": "",
                "status_code": 500,
                "target_id": target,
                "error": str(e)
            }

    async def parse(self, raw: dict) -> list[dict]:
        if not raw.get("html"):
            return []
            
        soup = BeautifulSoup(raw["html"], "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            if "linkedin.com/jobs/view" in a["href"]:
                if a["href"] not in links:
                    links.append(a["href"])
                    
        if not links:
            return []
            
        # Reverse to get newest posts (bottom of telegram channel), strictly limit to 10 jobs
        recent_links = list(reversed(links))[:10]
            
        parsed_jobs = []
        async with httpx.AsyncClient(verify=False, timeout=10.0, headers=self.headers) as client:
            for link in recent_links:
                try:
                    response = await client.get(link)
                    if response.status_code == 200:
                        job_soup = BeautifulSoup(response.text, "html.parser")
                        
                        title = "Unknown Telegram Job"
                        desc = ""
                        company_name = "Unknown Company"
                        experience_level = None
                        requirements = None
                        seniority_level = None
                        
                        # Try to parse JSON-LD first for robust full requirements
                        import json
                        ld_script = job_soup.find("script", type="application/ld+json")
                        if ld_script and ld_script.string:
                            try:
                                ld_data = json.loads(ld_script.string.strip())
                                title = ld_data.get("title", title)
                                
                                raw_desc = ld_data.get("description", "")
                                # Remove HTML tags from the JSON-LD rich description
                                desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n").strip() if raw_desc else ""
                                
                                hiring_org = ld_data.get("hiringOrganization", {})
                                if isinstance(hiring_org, dict):
                                    company_name = hiring_org.get("name", company_name)
                                    
                                exp_req = ld_data.get("experienceRequirements", {})
                                if isinstance(exp_req, dict) and exp_req.get("monthsOfExperience"):
                                    mons = exp_req.get("monthsOfExperience", 0)
                                    experience_level = f"{int(mons)//12} years" if int(mons) >= 12 else f"{mons} months"
                                elif isinstance(exp_req, str):
                                    experience_level = exp_req
                                    
                                reqs = ld_data.get("qualifications", "")
                                if reqs:
                                    requirements = BeautifulSoup(reqs, "html.parser").get_text(separator="\n").strip() if "<" in reqs else reqs

                            except Exception as e:
                                logger.error(f"Failed parsing JSON-LD: {e}")
                        
                        # Fallback to OG tags if JSON-LD is missing or failed
                        if not desc:
                            title_tag = job_soup.find("title")
                            title = title_tag.text.strip() if title_tag else title
                            desc_tag = job_soup.find("meta", property="og:description")
                            desc = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
                            
                        import re
                        if not experience_level and desc:
                            exp_match = re.search(r'((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten))\+?\s*(?:to|-)?\s*(?:\d+)?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)', desc, re.IGNORECASE)
                            if exp_match:
                                experience_level = exp_match.group(0).strip()
                                
                        if not seniority_level and desc:
                            if re.search(r'\b(?:senior|lead|principal|staff)\b', title + " " + desc, re.IGNORECASE):
                                seniority_level = "senior"
                            elif re.search(r'\b(?:junior|entry|intern|fresh)\b', title + " " + desc, re.IGNORECASE):
                                seniority_level = "junior"
                            elif re.search(r'\b(?:mid|intermediate|mid-level)\b', title + " " + desc, re.IGNORECASE):
                                seniority_level = "mid"
                                
                        if not requirements and desc:
                            req_match = re.search(r'(?i)(?:requirements?|qualifications?|what you\'ll need|what we\'re looking for)[:\s\n]+(.*?)(?:\n\n[A-Z]|$)', desc, re.DOTALL)
                            if req_match:
                                requirements = req_match.group(1).strip()[:1000] # clamp length
                        
                        parsed_job = {
                            "source_type": self.source_type,
                            "source_name": self.name,
                            "source_job_id": None, 
                            "source_url": link,
                            "title": title,
                            "description_text": desc,
                            "description_html": response.text,  # storing full html to be projected
                            "company_name": company_name,
                            "experience_level": experience_level,
                            "requirements": requirements,
                            "seniority_level": seniority_level,
                            "raw_payload": {"telegram_source": raw.get("source_url")}
                        }
                        parsed_jobs.append(parsed_job)
                except Exception as e:
                    logger.error(f"Failed to extract from LinkedIn URL {link}: {str(e)}")

        return parsed_jobs
