"""
Text processing utilities for cleaning and normalizing extracted content.
"""

import html
import re
from typing import List, Optional
from bs4 import BeautifulSoup


class TextProcessor:
    """Utilities for processing and cleaning text content."""
    
    def __init__(self):
        # Common patterns for text cleaning
        self.whitespace_pattern = re.compile(r'\s+')
        self.html_tag_pattern = re.compile(r'<[^>]+>')
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        
    def clean_html(self, content: str) -> str:
        """Remove HTML tags and clean up text content."""
        if not content:
            return ""
        
        try:
            # Parse with BeautifulSoup for better HTML handling
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
            
            # Decode HTML entities
            text = html.unescape(text)
            
            # Normalize whitespace
            text = self.whitespace_pattern.sub(' ', text)
            
            return text.strip()
            
        except Exception:
            # Fallback to simple regex cleaning
            text = self.html_tag_pattern.sub('', content)
            text = html.unescape(text)
            text = self.whitespace_pattern.sub(' ', text)
            return text.strip()
    
    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        if not text:
            return ""
        
        return self.whitespace_pattern.sub(' ', text).strip()
    
    def extract_sentences_around_email(self, text: str, email: str, context_sentences: int = 2) -> str:
        """Extract sentences around an email address for context."""
        if not text or not email:
            return ""
        
        try:
            # Find the email position
            email_pos = text.lower().find(email.lower())
            if email_pos == -1:
                return ""
            
            # Split into sentences (simple approach)
            sentences = re.split(r'[.!?]+', text)
            
            # Find which sentence contains the email
            current_pos = 0
            email_sentence_idx = -1
            
            for i, sentence in enumerate(sentences):
                sentence_end = current_pos + len(sentence)
                if current_pos <= email_pos <= sentence_end:
                    email_sentence_idx = i
                    break
                current_pos = sentence_end + 1  # +1 for the delimiter
            
            if email_sentence_idx == -1:
                return text[max(0, email_pos - 100):email_pos + 100]
            
            # Get surrounding sentences
            start_idx = max(0, email_sentence_idx - context_sentences)
            end_idx = min(len(sentences), email_sentence_idx + context_sentences + 1)
            
            context_sentences_list = sentences[start_idx:end_idx]
            context = '. '.join(s.strip() for s in context_sentences_list if s.strip())
            
            return context
            
        except Exception:
            # Fallback to simple character-based context
            start = max(0, email_pos - 200)
            end = min(len(text), email_pos + 200)
            return text[start:end]
    
    def clean_extracted_name(self, name: str) -> Optional[str]:
        """Clean and validate an extracted name."""
        if not name:
            return None
        
        # Remove extra whitespace
        name = self.normalize_whitespace(name)
        
        # Remove common prefixes/suffixes
        prefixes = ['mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'madam']
        suffixes = ['jr', 'sr', 'phd', 'md', 'esq']
        
        words = name.lower().split()
        cleaned_words = []
        
        for word in words:
            word_clean = word.strip('.,')
            if word_clean not in prefixes and word_clean not in suffixes:
                cleaned_words.append(word_clean.capitalize())
        
        if len(cleaned_words) >= 1:
            return ' '.join(cleaned_words)
        
        return None
    
    def clean_extracted_phone(self, phone: str) -> Optional[str]:
        """Clean and format an extracted phone number."""
        if not phone:
            return None
        
        # Remove all non-digit and non-plus characters
        digits_only = re.sub(r'[^\d+]', '', phone)
        
        # Basic validation
        if len(digits_only) < 7 or len(digits_only) > 15:
            return None
        
        # Format common patterns
        if digits_only.startswith('+1') and len(digits_only) == 12:
            # US number with country code
            return f"+1 ({digits_only[2:5]}) {digits_only[5:8]}-{digits_only[8:]}"
        elif len(digits_only) == 10:
            # US number without country code
            return f"({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}"
        elif digits_only.startswith('+'):
            # International number
            return f"+{digits_only[1:]}"
        
        return digits_only
    
    def extract_domain_from_email(self, email: str) -> Optional[str]:
        """Extract and clean domain from email address."""
        if not email or '@' not in email:
            return None
        
        try:
            domain = email.split('@')[1].lower()
            # Remove any trailing characters that shouldn't be in domain
            domain = re.sub(r'[^a-z0-9.-].*$', '', domain)
            return domain if '.' in domain else None
        except Exception:
            return None
    
    def is_likely_person_name(self, text: str) -> bool:
        """Determine if text is likely a person's name."""
        if not text or len(text) < 2 or len(text) > 50:
            return False
        
        # Should contain mostly letters and spaces
        letter_count = sum(1 for c in text if c.isalpha())
        if letter_count / len(text) < 0.7:
            return False
        
        # Should start with capital letter
        if not text[0].isupper():
            return False
        
        # Common non-name patterns
        non_name_words = {
            'email', 'contact', 'info', 'admin', 'support', 'sales',
            'marketing', 'webmaster', 'help', 'service', 'team'
        }
        
        words = text.lower().split()
        if any(word in non_name_words for word in words):
            return False
        
        return True
    
    def extract_text_between_markers(self, text: str, start_marker: str, end_marker: str) -> List[str]:
        """Extract text between specific markers."""
        if not text or not start_marker:
            return []
        
        results = []
        start_pos = 0
        
        while True:
            start_idx = text.find(start_marker, start_pos)
            if start_idx == -1:
                break
            
            start_idx += len(start_marker)
            
            if end_marker:
                end_idx = text.find(end_marker, start_idx)
                if end_idx == -1:
                    break
                extracted = text[start_idx:end_idx]
            else:
                # Extract to end of line if no end marker
                end_idx = text.find('\n', start_idx)
                if end_idx == -1:
                    extracted = text[start_idx:]
                else:
                    extracted = text[start_idx:end_idx]
            
            extracted = extracted.strip()
            if extracted:
                results.append(extracted)
            
            start_pos = end_idx + (len(end_marker) if end_marker else 1)
        
        return results
    
    def remove_duplicate_spaces(self, text: str) -> str:
        """Remove duplicate spaces and normalize whitespace."""
        if not text:
            return ""
        
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        
        # Replace multiple newlines with single newline
        text = re.sub(r'\n+', '\n', text)
        
        # Replace tabs with spaces
        text = text.replace('\t', ' ')
        
        return text.strip()
    
    def truncate_text(self, text: str, max_length: int = 200, suffix: str = "...") -> str:
        """Truncate text to specified length with suffix."""
        if not text or len(text) <= max_length:
            return text
        
        # Try to break at word boundary
        truncated = text[:max_length - len(suffix)]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.7:  # If we can find a reasonable word boundary
            truncated = truncated[:last_space]
        
        return truncated + suffix
    
    def clean_company_name(self, company: str) -> Optional[str]:
        """Clean and normalize company name."""
        if not company:
            return None
        
        # Remove extra whitespace
        company = self.normalize_whitespace(company)
        
        # Common company suffixes that should be properly capitalized
        company_suffixes = {
            'inc': 'Inc',
            'corp': 'Corp',
            'ltd': 'Ltd',
            'llc': 'LLC',
            'co': 'Co',
            'company': 'Company',
            'corporation': 'Corporation',
            'limited': 'Limited'
        }
        
        words = company.split()
        cleaned_words = []
        
        for word in words:
            word_clean = word.strip('.,')
            word_lower = word_clean.lower()
            
            if word_lower in company_suffixes:
                cleaned_words.append(company_suffixes[word_lower])
            elif word_clean:
                cleaned_words.append(word_clean.capitalize())
        
        if cleaned_words:
            return ' '.join(cleaned_words)
        
        return None
    
    def extract_structured_data(self, text: str, patterns: dict) -> dict:
        """Extract structured data using provided patterns."""
        results = {}
        
        for key, pattern in patterns.items():
            matches = pattern.findall(text)
            if matches:
                # Take the first match or all matches depending on the pattern
                if len(matches) == 1:
                    results[key] = matches[0] if isinstance(matches[0], str) else ' '.join(matches[0])
                else:
                    results[key] = matches
        
        return results
    
    def clean_extracted_title(self, title: str) -> Optional[str]:
        """Clean and normalize job title."""
        if not title:
            return None
        
        # Remove extra whitespace
        title = self.normalize_whitespace(title)
        
        # Remove common prefixes that aren't part of the title
        prefixes_to_remove = ['position:', 'title:', 'role:', 'job:']
        title_lower = title.lower()
        
        for prefix in prefixes_to_remove:
            if title_lower.startswith(prefix):
                title = title[len(prefix):].strip()
                break
        
        # Capitalize properly
        # Words that should typically be lowercase in titles
        lowercase_words = {'of', 'and', 'the', 'for', 'at', 'in', 'on', 'to', 'a', 'an'}
        
        words = title.split()
        capitalized_words = []
        
        for i, word in enumerate(words):
            word_clean = word.strip('.,')
            if i == 0 or word_clean.lower() not in lowercase_words:
                capitalized_words.append(word_clean.capitalize())
            else:
                capitalized_words.append(word_clean.lower())
        
        if capitalized_words:
            return ' '.join(capitalized_words)
        
        return None