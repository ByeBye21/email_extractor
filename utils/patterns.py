"""
Pattern definitions for email and contact information extraction.
Contains regex patterns for emails, names, phone numbers, and social profiles.
"""

import re
from typing import Dict, List

class EmailPatterns:
    """Email detection patterns with various levels of strictness."""
    
    def __init__(self):
        self.email_patterns = {
            # Standard email pattern (most permissive)
            'standard': re.compile(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                re.IGNORECASE
            ),
            
            # Strict email pattern (more validation)
            'strict': re.compile(
                r'\b[A-Za-z0-9]([A-Za-z0-9._%-]*[A-Za-z0-9])?@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}\b',
                re.IGNORECASE
            ),
            
            # Email with surrounding context
            'with_context': re.compile(
                r'(?:email|e-mail|contact)?\s*:?\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})',
                re.IGNORECASE
            ),
            
            # Email in quotes or parentheses
            'quoted': re.compile(
                r'["\'(]([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})["\')]',
                re.IGNORECASE
            ),
        }

class ContactPatterns:
    """Patterns for extracting contact information."""
    
    def __init__(self):
        # Name patterns
        self.name_patterns = [
            # First Last name pattern
            re.compile(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'),
            # First Middle Last pattern
            re.compile(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'),
            # Name with title (Dr., Mr., etc.)
            re.compile(r'\b(?:Dr|Mr|Ms|Mrs|Prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'),
            # Name followed by comma (often in listings)
            re.compile(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+),'),
        ]
        
        # Phone number patterns
        self.phone_patterns = [
            # US format: (555) 123-4567
            re.compile(r'\((\d{3})\)\s*(\d{3})-(\d{4})'),
            # International format: +1-555-123-4567
            re.compile(r'\+(\d{1,3})-(\d{3})-(\d{3})-(\d{4})'),
            # Simple format: 555-123-4567
            re.compile(r'(\d{3})-(\d{3})-(\d{4})'),
            # Dot format: 555.123.4567
            re.compile(r'(\d{3})\.(\d{3})\.(\d{4})'),
            # Space format: 555 123 4567
            re.compile(r'(\d{3})\s+(\d{3})\s+(\d{4})'),
            # International with country code
            re.compile(r'\+(\d{1,3})\s*\((\d{1,4})\)\s*(\d{3,4})-?(\d{4})'),
        ]
        
        # Job title patterns
        self.job_title_patterns = [
            # Common titles
            re.compile(r'\b(CEO|CTO|CFO|COO|President|Vice President|VP|Director|Manager|Senior Manager)\b', re.IGNORECASE),
            # Engineering titles
            re.compile(r'\b(Software Engineer|Senior Software Engineer|Lead Engineer|Principal Engineer|Architect|Tech Lead)\b', re.IGNORECASE),
            # Business titles
            re.compile(r'\b(Business Analyst|Product Manager|Project Manager|Account Manager|Sales Manager)\b', re.IGNORECASE),
            # Marketing titles
            re.compile(r'\b(Marketing Manager|Digital Marketing Specialist|Content Manager|SEO Specialist)\b', re.IGNORECASE),
            # Generic pattern for titles
            re.compile(r'\b(Senior|Junior|Lead|Principal|Chief)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'),
            # Title followed by common words
            re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Manager|Director|Engineer|Analyst|Specialist|Coordinator)\b'),
        ]
        
        # Company name patterns
        self.company_patterns = [
            # Company with legal suffix
            re.compile(r'\b([A-Z][A-Za-z\s&]+)\s+(?:Inc|Corp|LLC|Ltd|Co|Company|Corporation|Limited)\b\.?'),
            # Company with "at" or "with"
            re.compile(r'\b(?:at|with)\s+([A-Z][A-Za-z\s&]+)(?:\s|$)', re.IGNORECASE),
            # Company in quotes
            re.compile(r'"([A-Z][A-Za-z\s&]+)"'),
            # Simple company pattern (2-4 words starting with capital)
            re.compile(r'\b([A-Z][A-Za-z]+(?:\s+[A-Z&][A-Za-z]*){1,3})\b'),
        ]

class SocialPatterns:
    """Patterns for social media profile detection."""
    
    def __init__(self):
        self.patterns = {
            'linkedin': re.compile(r'linkedin\.com/in/([a-zA-Z0-9\-_]+)', re.IGNORECASE),
            'twitter': re.compile(r'twitter\.com/([a-zA-Z0-9_]+)', re.IGNORECASE),
            'facebook': re.compile(r'facebook\.com/([a-zA-Z0-9.]+)', re.IGNORECASE),
            'instagram': re.compile(r'instagram\.com/([a-zA-Z0-9_.]+)', re.IGNORECASE),
            'github': re.compile(r'github\.com/([a-zA-Z0-9\-_]+)', re.IGNORECASE),
            'youtube': re.compile(r'youtube\.com/(?:c/|channel/|user/)?([a-zA-Z0-9\-_]+)', re.IGNORECASE),
            'tiktok': re.compile(r'tiktok\.com/@([a-zA-Z0-9_.]+)', re.IGNORECASE),
        }

class ObfuscationPatterns:
    """Patterns for detecting obfuscated emails and contact info."""
    
    def __init__(self):
        self.email_obfuscation = [
            # [at] and [dot] replacements
            re.compile(r'([a-zA-Z0-9._-]+)\s*\[at\]\s*([a-zA-Z0-9.-]+)\s*\[dot\]\s*([a-zA-Z]{2,})', re.IGNORECASE),
            # (at) and (dot) replacements
            re.compile(r'([a-zA-Z0-9._-]+)\s*\(at\)\s*([a-zA-Z0-9.-]+)\s*\(dot\)\s*([a-zA-Z]{2,})', re.IGNORECASE),
            # "at" and "dot" word replacements
            re.compile(r'([a-zA-Z0-9._-]+)\s+at\s+([a-zA-Z0-9.-]+)\s+dot\s+([a-zA-Z]{2,})', re.IGNORECASE),
            # Spaces around @ and .
            re.compile(r'([a-zA-Z0-9._-]+)\s*@\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z]{2,})'),
            # HTML entity obfuscation
            re.compile(r'([a-zA-Z0-9._-]+)@([a-zA-Z0-9.-]+).([a-zA-Z]{2,})'),
            # Unicode obfuscation
            re.compile(r'([a-zA-Z0-9._-]+)＠([a-zA-Z0-9.-]+)．([a-zA-Z]{2,})'),
        ]
        
        # Phone obfuscation patterns
        self.phone_obfuscation = [
            # Dots instead of dashes
            re.compile(r'(\d{3})\.(\d{3})\.(\d{4})'),
            # Spaces instead of dashes
            re.compile(r'(\d{3})\s+(\d{3})\s+(\d{4})'),
            # Mixed separators
            re.compile(r'(\d{3})-(\d{3})\.(\d{4})'),
            # With text separators
            re.compile(r'(\d{3})\s*dash\s*(\d{3})\s*dash\s*(\d{4})', re.IGNORECASE),
        ]

class ContextPatterns:
    """Patterns for understanding context around contact information."""
    
    def __init__(self):
        # Patterns that indicate contact information is nearby
        self.contact_indicators = [
            re.compile(r'\b(?:contact|reach|email|call|phone|tel|mobile|office)\b', re.IGNORECASE),
            re.compile(r'\b(?:get in touch|reach out|contact us|call us)\b', re.IGNORECASE),
            re.compile(r'\b(?:for more information|questions|inquiries)\b', re.IGNORECASE),
        ]
        
        # Patterns for role/title indicators
        self.role_indicators = [
            re.compile(r'\b(?:position|title|role|job|work as|serves as)\b', re.IGNORECASE),
            re.compile(r'\b(?:responsible for|manages|leads|heads)\b', re.IGNORECASE),
        ]
        
        # Patterns for company indicators
        self.company_indicators = [
            re.compile(r'\b(?:works at|employed by|company|organization|firm)\b', re.IGNORECASE),
            re.compile(r'\b(?:member of|part of|team at)\b', re.IGNORECASE),
        ]
        
        # Patterns for location indicators
        self.location_indicators = [
            re.compile(r'\b(?:located in|based in|office in|address)\b', re.IGNORECASE),
            re.compile(r'\b(?:city|state|country|zip|postal)\b', re.IGNORECASE),
        ]

class ValidationPatterns:
    """Patterns for validating extracted information."""
    
    def __init__(self):
        # Invalid email patterns (common false positives)
        self.invalid_email_patterns = [
            re.compile(r'\.{2,}'),  # Multiple consecutive dots
            re.compile(r'^\.|\.$'),  # Starting or ending with dot
            re.compile(r'@\.'),  # @ followed by dot
            re.compile(r'\.@'),  # Dot followed by @
            re.compile(r'@.*@'),  # Multiple @ symbols
        ]
        
        # Common non-name patterns to exclude
        self.non_name_patterns = [
            re.compile(r'\b(?:email|contact|info|admin|webmaster|support|sales|marketing)\b', re.IGNORECASE),
            re.compile(r'\b(?:lorem|ipsum|dolor|sit|amet)\b', re.IGNORECASE),  # Lorem ipsum text
            re.compile(r'\b(?:click|here|more|read|view|download)\b', re.IGNORECASE),  # UI text
        ]
        
        # Valid domain patterns
        self.valid_domain_pattern = re.compile(
            r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
        )
        
        # Common disposable email domains to flag
        self.disposable_domains = {
            '10minutemail.com', 'tempmail.org', 'guerrillamail.com',
            'mailinator.com', 'yopmail.com', 'temp-mail.org'
        }
