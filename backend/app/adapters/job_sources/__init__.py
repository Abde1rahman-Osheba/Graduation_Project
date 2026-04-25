from app.adapters.job_sources.base import BaseJobSourceAdapter
from app.adapters.job_sources.generic_html import GenericHtmlListingAdapter
from app.adapters.job_sources.telegram_channel import TelegramChannelAdapter

__all__ = [
    "BaseJobSourceAdapter",
    "GenericHtmlListingAdapter",
    "TelegramChannelAdapter"
]
