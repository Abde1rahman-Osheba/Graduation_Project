"""
PATHS Backend — Generic HTML Listing Adapter.
"""
import httpx
import re
import logging
from app.adapters.job_sources.base import BaseJobSourceAdapter

logger = logging.getLogger(__name__)

class GenericHtmlListingAdapter(BaseJobSourceAdapter):
    name = "generic_html"
    source_type = "generic_html"
    
    def __init__(self, max_pages: int = 10):
        self.max_pages = max_pages

    async def discover(self, query: dict | None = None) -> list[str]:
        # Simple implementation: accept explicit URLs in query
        if query and "urls" in query:
            return query["urls"][:self.max_pages]
        return []

    async def fetch(self, target: str) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
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
            
        html = raw["html"]
        # Very rudimentary parse using regex for structural HTML
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else "Unknown Job Title"
        
        text_desc = re.sub(r'<[^>]+>', ' ', html).strip()
        text_desc = re.sub(r'\s+', ' ', text_desc)

        parsed_job = {
            "source_type": self.source_type,
            "source_name": self.name,
            "source_job_id": None, 
            "source_url": raw.get("source_url", ""),
            "title": title,
            "description_text": text_desc,
            "description_html": html,
            "company_name": "Unknown Company",
            "raw_payload": raw
        }
        
        return [parsed_job]
