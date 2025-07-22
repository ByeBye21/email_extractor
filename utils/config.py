"""
Configuration management for the email extractor.
"""

import os
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config(BaseModel):
    """Configuration settings for the email extractor."""
    
    # Crawling settings
    max_depth: int = Field(default=5, ge=1, le=20)
    max_pages: int = Field(default=1000, ge=1)
    delay: float = Field(default=1.0, ge=0.1, le=10.0)
    user_agent: str = Field(default="EmailExtractor/1.0 (+https://github.com/example/email-extractor)")
    
    # Output settings
    output_format: str = Field(default="csv", pattern=r"^(csv|json|excel)$")
    output_dir: str = Field(default="results")
    output_file: Optional[str] = None
    
    # Processing options
    validate_emails: bool = Field(default=False)
    use_javascript: bool = Field(default=False)
    extract_social: bool = Field(default=False)
    ocr_emails: bool = Field(default=False)
    
    # Filtering options
    allowed_domains: Optional[List[str]] = None
    excluded_domains: Optional[List[str]] = None
    excluded_extensions: List[str] = Field(default=[".pdf", ".doc", ".docx", ".zip", ".rar"])
    
    # Rate limiting
    requests_per_second: float = Field(default=1.0, ge=0.1, le=10.0)
    concurrent_requests: int = Field(default=3, ge=1, le=10)
    
    # Retry settings
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=2.0, ge=0.1, le=60.0)
    
    # CRM Integration (optional)
    salesforce_username: Optional[str] = Field(default=None)
    salesforce_password: Optional[str] = Field(default=None)
    salesforce_token: Optional[str] = Field(default=None)
    hubspot_api_key: Optional[str] = Field(default=None)
    
    # Advanced settings
    ignore_robots_txt: bool = Field(default=False)
    custom_headers: Optional[dict] = None
    proxy_url: Optional[str] = None

    # Extraction settings
    extract_titles: bool = Field(default=True)
    extract_full_names: bool = Field(default=True) 
    context_window: int = Field(default=300)
    academic_mode: bool = Field(default=True)

    class Config:
        env_prefix = "EMAIL_EXTRACTOR_"

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls(
            max_depth=int(os.getenv("EMAIL_EXTRACTOR_MAX_DEPTH", "3")),
            max_pages=int(os.getenv("EMAIL_EXTRACTOR_MAX_PAGES", "1000")),
            delay=float(os.getenv("EMAIL_EXTRACTOR_DELAY", "1.0")),
            user_agent=os.getenv("EMAIL_EXTRACTOR_USER_AGENT", "EmailExtractor/1.0"),
            output_format=os.getenv("EMAIL_EXTRACTOR_OUTPUT_FORMAT", "csv"),
            output_dir=os.getenv("EMAIL_EXTRACTOR_OUTPUT_DIR", "results"),
            validate_emails=os.getenv("EMAIL_EXTRACTOR_VALIDATE_EMAILS", "false").lower() == "true",
            use_javascript=os.getenv("EMAIL_EXTRACTOR_USE_JAVASCRIPT", "false").lower() == "true",
            extract_social=os.getenv("EMAIL_EXTRACTOR_EXTRACT_SOCIAL", "false").lower() == "true",
            ocr_emails=os.getenv("EMAIL_EXTRACTOR_OCR_EMAILS", "false").lower() == "true",
            salesforce_username=os.getenv("SALESFORCE_USERNAME"),
            salesforce_password=os.getenv("SALESFORCE_PASSWORD"),
            salesforce_token=os.getenv("SALESFORCE_TOKEN"),
            hubspot_api_key=os.getenv("HUBSPOT_API_KEY"),
            proxy_url=os.getenv("EMAIL_EXTRACTOR_PROXY_URL"),
        )

    def __str__(self) -> str:
        """String representation of config (hiding sensitive data)."""
        safe_dict = self.dict()
        # Hide sensitive information
        sensitive_keys = ['salesforce_password', 'salesforce_token', 'hubspot_api_key']
        for key in sensitive_keys:
            if safe_dict.get(key):
                safe_dict[key] = "***"
        return f"Config({safe_dict})"
