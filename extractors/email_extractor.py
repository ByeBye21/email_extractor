"""
Email Extractor - Advanced email detection from multiple sources
Handles standard emails, obfuscated formats, mailto links, base64, JS-rendered, and OCR.
"""

import base64
import logging
import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import unquote, urlparse
import html
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup

# Optional imports with fallbacks
try:
    import pytesseract
    from PIL import Image
    import requests
    from io import BytesIO
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logging.warning("OCR dependencies not available. Install pytesseract and Pillow for image email extraction.")

from utils.patterns import EmailPatterns, SocialPatterns
from utils.text_processing import TextProcessor


class EmailExtractor:
    """Advanced email extraction with multiple detection methods."""
    
    def __init__(self, config):
        self.config = config
        self.patterns = EmailPatterns()
        self.social_patterns = SocialPatterns()
        self.text_processor = TextProcessor()
        
        # Configure OCR if enabled
        if config.ocr_emails and OCR_AVAILABLE:
            try:
                # Test if tesseract is available
                pytesseract.get_tesseract_version()
                self.ocr_available = True
                logging.info("OCR enabled for email extraction")
            except Exception as e:
                logging.warning(f"OCR not available: {e}")
                self.ocr_available = False
        else:
            self.ocr_available = False
    
    def extract_emails(self, content: str, source_url: str) -> List[Dict]:
        """Extract emails using all enhanced methods."""
        found_emails = set()
        email_details = []
        
        try:
            logging.info(f"Extracting emails from {source_url}")
            soup = BeautifulSoup(content, 'html.parser')
            
            # Method 1: Enhanced mailto links (MOST IMPORTANT)
            mailto_emails = self._extract_mailto_links_enhanced(soup, source_url)
            for email_data in mailto_emails:
                if email_data['email'] not in found_emails:
                    found_emails.add(email_data['email'])
                    email_details.append(email_data)
            
            # Method 2: Enhanced standard patterns
            standard_emails = self._extract_standard_emails_enhanced(content, source_url)
            for email_data in standard_emails:
                if email_data['email'] not in found_emails:
                    found_emails.add(email_data['email'])
                    email_details.append(email_data)
            
            # Method 3: Enhanced obfuscated emails
            obfuscated_emails = self._extract_obfuscated_emails_enhanced(content, soup)
            for email_data in obfuscated_emails:
                if email_data['email'] not in found_emails:
                    found_emails.add(email_data['email'])
                    email_details.append(email_data)
            
            logging.info(f"Extracted {len(email_details)} unique emails from {source_url}")
            return email_details
            
        except Exception as e:
            logging.error(f"Error extracting emails from {source_url}: {e}")
            return []

    def _extract_standard_emails_enhanced(self, content: str, source_url: str) -> List[Dict]:
        """Standard email extraction with debugging."""
        emails = []
        
        # Less aggressive text cleaning
        text_content = self._clean_html_preserve_emails(content)
        
        logging.debug(f"Text content length after cleaning: {len(text_content)}")
        logging.debug(f"Sample text: {text_content[:200]}...")
        
        # Email patterns
        enhanced_patterns = {
            'basic': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', re.IGNORECASE),
            'relaxed': re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', re.IGNORECASE),
            'with_context': re.compile(r'(?:email|e-mail|mail|contact)?\s*:?\s*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})', re.IGNORECASE),
            'quoted': re.compile(r'["\'(]([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})["\')]', re.IGNORECASE),
        }
        
        for pattern_name, pattern in enhanced_patterns.items():
            matches = list(pattern.finditer(text_content))
            logging.debug(f"Pattern '{pattern_name}' found {len(matches)} potential matches")
            
            for match in matches:
                if pattern_name == 'with_context' and match.groups():
                    email = match.group(1).lower().strip()
                else:
                    email = match.group().lower().strip()
                
                # Clean up the email
                email = email.strip('"\'()[]{}')
                
                # Enhanced validation
                if self._is_valid_email_format_enhanced(email):
                    logging.debug(f"Valid email found: {email}")
                    emails.append({
                        'email': email,
                        'method': f'standard_{pattern_name}',
                        'pattern': pattern_name,
                        'confidence': 0.9 if pattern_name == 'basic' else 0.8,
                        'context': self._get_context_enhanced(text_content, match.start(), match.end()),
                        'source_url': source_url
                    })
                else:
                    logging.debug(f"Invalid email rejected: {email}")
        
        return emails

    # Enhanced HTML cleaning that preserves emails:

    def _clean_html_preserve_emails(self, content: str) -> str:
        """Clean HTML but preserve email-containing text better."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements but keep their text if it contains @
            for script in soup(["script", "style"]):
                if script.string and '@' in script.string:
                    # Keep script content that might have emails
                    script.replace_with(f" {script.string} ")
                else:
                    script.decompose()
            
            # Get text content
            text = soup.get_text(separator=' ')
            
            # Decode HTML entities
            text = html.unescape(text)
            
            # Normalize whitespace but preserve line breaks around emails
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                if '@' in line:
                    # Preserve lines with @ symbols with minimal cleaning
                    cleaned_lines.append(' '.join(line.split()))
                else:
                    # Normal cleaning for other lines
                    cleaned = ' '.join(line.split())
                    if cleaned:
                        cleaned_lines.append(cleaned)
            
            return '\n'.join(cleaned_lines)
            
        except Exception as e:
            logging.debug(f"HTML cleaning error: {e}")
            # Fallback to simple cleaning
            return re.sub(r'<[^>]+>', ' ', content)

    # ADD enhanced email validation:

    def _is_valid_email_format_enhanced(self, email: str) -> bool:
        """Enhanced email format validation with better patterns."""
        if not email or len(email) < 5 or len(email) > 254:
            return False
        
        # Must contain exactly one @
        if email.count('@') != 1:
            return False
        
        try:
            local, domain = email.split('@')
        except ValueError:
            return False
        
        # Basic checks
        if not local or not domain:
            return False
        
        if len(local) > 64 or len(domain) > 255:
            return False
        
        # Domain must have at least one dot
        if '.' not in domain:
            return False
        
        # Enhanced pattern validation
        email_pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
            re.IGNORECASE
        )
        
        if not email_pattern.match(email):
            return False
        
        # Check for common invalid patterns
        invalid_patterns = [
            r'\.{2,}',      # Multiple consecutive dots
            r'^\.|\.$',     # Starting or ending with dot
            r'@\.',         # @ followed by dot
            r'\.@',         # Dot followed by @
            r'^-|^_',       # Starting with dash or underscore
            r'-$|_$',       # Ending with dash or underscore
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, email):
                return False
        
        # Check for minimum domain structure
        domain_parts = domain.split('.')
        if len(domain_parts) < 2:
            return False
        
        # Last part should be valid TLD (at least 2 chars)
        if len(domain_parts[-1]) < 2:
            return False
        
        return True

    # ADD enhanced context extraction:

    def _get_context_enhanced(self, text: str, start: int, end: int, context_length: int = 150) -> str:
        """Enhanced context extraction around email matches."""
        try:
            # Get wider context
            start_context = max(0, start - context_length)
            end_context = min(len(text), end + context_length)
            
            context = text[start_context:end_context].strip()
            
            # Clean up whitespace but preserve structure
            context = re.sub(r'\s+', ' ', context)
            
            # If context is too long, try to break at sentence boundaries
            if len(context) > 300:
                sentences = re.split(r'[.!?]', context)
                if len(sentences) > 1:
                    # Keep middle sentences that contain the email
                    middle_idx = len(sentences) // 2
                    context = '. '.join(sentences[max(0, middle_idx-1):middle_idx+2])
            
            return context
        except Exception:
            return ""

    # ADD enhanced obfuscated email extraction:

    def _extract_obfuscated_emails_enhanced(self, content: str, soup: BeautifulSoup) -> List[Dict]:
        """Enhanced obfuscated email extraction with more patterns."""
        emails = []
        
        text_content = self._clean_html_preserve_emails(content)
        
        # Enhanced obfuscation patterns
        obfuscation_patterns = [
            # Standard obfuscations
            (r'([a-zA-Z0-9._-]+)\s*@\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z]{2,})', 
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            (r'([a-zA-Z0-9._-]+)\s*\[at\]\s*([a-zA-Z0-9.-]+)\s*\[dot\]\s*([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            (r'([a-zA-Z0-9._-]+)\s*\(at\)\s*([a-zA-Z0-9.-]+)\s*\(dot\)\s*([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # Word replacements
            (r'([a-zA-Z0-9._-]+)\s+at\s+([a-zA-Z0-9.-]+)\s+dot\s+([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # HTML entities
            (r'([a-zA-Z0-9._-]+)&#64;([a-zA-Z0-9.-]+)&#46;([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # Unicode variants
            (r'([a-zA-Z0-9._-]+)＠([a-zA-Z0-9.-]+)．([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # Multiple dots/spaces
            (r'([a-zA-Z0-9._-]+)\s*@\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z]{2,})',
            lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}.{m.group(4)}"),
        ]
        
        for pattern, deobfuscator in obfuscation_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            
            for match in matches:
                try:
                    email = deobfuscator(match).lower()
                    
                    if self._is_valid_email_format_enhanced(email):
                        emails.append({
                            'email': email,
                            'method': 'deobfuscation',
                            'confidence': 0.85,
                            'context': self._get_context_enhanced(text_content, match.start(), match.end()),
                            'original_text': match.group()
                        })
                        
                except Exception as e:
                    logging.debug(f"Error deobfuscating email {match.group()}: {e}")
        
        return emails
    
    def _extract_standard_emails(self, content: str) -> List[Dict]:
        """Extract emails using standard regex patterns."""
        emails = []
        
        # Remove HTML tags for text-only search
        text_content = self.text_processor.clean_html(content)
        
        # Apply multiple patterns for better coverage
        for pattern_name, pattern in self.patterns.email_patterns.items():
            matches = pattern.finditer(text_content)
            
            for match in matches:
                email = match.group().lower().strip()
                
                # Basic validation
                if self._is_valid_email_format(email):
                    emails.append({
                        'email': email,
                        'method': 'standard_regex',
                        'pattern': pattern_name,
                        'confidence': 0.9,
                        'context': self._get_context(text_content, match.start(), match.end())
                    })
        
        return emails
    
    def _extract_mailto_links(self, soup: BeautifulSoup, source_url: str) -> List[Dict]:
        """Extract emails from mailto links."""
        emails = []
        
        # Find all mailto links
        mailto_links = soup.find_all('a', href=True)
        
        for link in mailto_links:
            href = link.get('href', '')
            
            if href.startswith('mailto:'):
                try:
                    # Parse mailto URL
                    email_part = href[7:]  # Remove 'mailto:'
                    
                    # Handle query parameters and multiple emails
                    if '?' in email_part:
                        email_part = email_part.split('?')[0]
                    
                    # Split multiple emails
                    email_addresses = [e.strip() for e in email_part.split(',')]
                    
                    for email in email_addresses:
                        email = unquote(email).lower()
                        
                        if self._is_valid_email_format(email):
                            # Get link text as context
                            link_text = link.get_text(strip=True)
                            
                            emails.append({
                                'email': email,
                                'method': 'mailto_link',
                                'confidence': 0.95,
                                'context': link_text,
                                'link_text': link_text,
                                'source_url': source_url
                            })
                            
                except Exception as e:
                    logging.debug(f"Error parsing mailto link {href}: {e}")
        
        return emails
    
    def _extract_obfuscated_emails(self, content: str, soup: BeautifulSoup) -> List[Dict]:
        """Extract obfuscated emails using various deobfuscation techniques."""
        emails = []
        
        # Common obfuscation patterns
        obfuscation_patterns = [
            # Spaces in email: user @ domain . com
            (r'([a-zA-Z0-9._-]+)\s*@\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z]{2,})', 
             lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # [at] and [dot] replacements
            (r'([a-zA-Z0-9._-]+)\s*\[at\]\s*([a-zA-Z0-9.-]+)\s*\[dot\]\s*([a-zA-Z]{2,})',
             lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # (at) and (dot) replacements
            (r'([a-zA-Z0-9._-]+)\s*\(at\)\s*([a-zA-Z0-9.-]+)\s*\(dot\)\s*([a-zA-Z]{2,})',
             lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
            
            # HTML entity obfuscation
            (r'([a-zA-Z0-9._-]+)&#64;([a-zA-Z0-9.-]+)&#46;([a-zA-Z]{2,})',
             lambda m: f"{m.group(1)}@{m.group(2)}.{m.group(3)}"),
        ]
        
        text_content = self.text_processor.clean_html(content)
        
        for pattern, deobfuscator in obfuscation_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            
            for match in matches:
                try:
                    email = deobfuscator(match).lower()
                    
                    if self._is_valid_email_format(email):
                        emails.append({
                            'email': email,
                            'method': 'deobfuscation',
                            'confidence': 0.85,
                            'context': self._get_context(text_content, match.start(), match.end()),
                            'original_text': match.group()
                        })
                        
                except Exception as e:
                    logging.debug(f"Error deobfuscating email {match.group()}: {e}")
        
        # Check for CSS/style hidden emails
        style_emails = self._extract_css_hidden_emails(soup)
        emails.extend(style_emails)
        
        return emails
    
    def _extract_css_hidden_emails(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract emails that might be hidden using CSS."""
        emails = []
        
        # Look for elements with email-like content but hidden via CSS
        hidden_selectors = [
            '[style*="display:none"]',
            '[style*="display: none"]',
            '[style*="visibility:hidden"]',
            '[style*="visibility: hidden"]',
            '.hidden',
            '.sr-only'
        ]
        
        for selector in hidden_selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    if text and '@' in text:
                        # Apply standard email extraction to hidden text
                        hidden_emails = self._extract_standard_emails(text)
                        for email_data in hidden_emails:
                            email_data['method'] = 'css_hidden'
                            email_data['confidence'] = 0.7
                            emails.append(email_data)
            except Exception as e:
                logging.debug(f"Error checking hidden elements: {e}")
        
        return emails
    
    def _extract_base64_emails(self, content: str) -> List[Dict]:
        """Extract base64 encoded emails."""
        emails = []
        
        # Look for base64 patterns that might contain emails
        base64_pattern = r'[A-Za-z0-9+/]{20,}={0,2}'
        matches = re.finditer(base64_pattern, content)
        
        for match in matches:
            try:
                encoded = match.group()
                # Try to decode
                decoded = base64.b64decode(encoded + '==').decode('utf-8', errors='ignore')
                
                # Check if decoded content contains emails
                decoded_emails = self._extract_standard_emails(decoded)
                for email_data in decoded_emails:
                    email_data['method'] = 'base64_decoded'
                    email_data['confidence'] = 0.8
                    email_data['encoded_form'] = encoded
                    emails.append(email_data)
                    
            except Exception:
                # Not valid base64 or doesn't contain emails
                continue
        
        return emails
    
    def _extract_js_emails(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract emails from JavaScript code."""
        emails = []
        
        # Find all script tags
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string:
                js_content = script.string
                
                # Look for common JS email patterns
                js_patterns = [
                    # String concatenation: 'user' + '@' + 'domain.com'
                    r"'([^']+)'\s*\+\s*'@'\s*\+\s*'([^']+)'",
                    r'"([^"]+)"\s*\+\s*"@"\s*\+\s*"([^"]+)"',
                    
                    # Variable assignments
                    r'email\s*[:=]\s*["\']([^"\']+@[^"\']+)["\']',
                    r'mail\s*[:=]\s*["\']([^"\']+@[^"\']+)["\']',
                ]
                
                for pattern in js_patterns:
                    matches = re.finditer(pattern, js_content, re.IGNORECASE)
                    
                    for match in matches:
                        if len(match.groups()) == 2:
                            # Concatenated email
                            email = f"{match.group(1)}@{match.group(2)}".lower()
                        else:
                            # Direct email
                            email = match.group(1).lower()
                        
                        if self._is_valid_email_format(email):
                            emails.append({
                                'email': email,
                                'method': 'javascript',
                                'confidence': 0.75,
                                'context': match.group()[:100]
                            })
        
        return emails
    
    def _extract_ocr_emails_sync(self, soup: BeautifulSoup, source_url: str) -> List[Dict]:
        """Extract emails from images using OCR."""

        if not self.ocr_available:
            logging.warning("OCR DEBUG: OCR not available")
            return []
        
        emails = []
        images = soup.find_all('img', src=True)
        logging.info(f"OCR DEBUG: Found {len(images)} images to process")
        
        for img in images:  # Process all images (removed [:5] limit)
            try:
                img_src = img.get('src')
                if not img_src:
                    continue
                
                # Get absolute URL
                if img_src.startswith('//'):
                    img_src = f"https:{img_src}"
                elif img_src.startswith('/'):
                    base_url = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
                    img_src = f"{base_url}{img_src}"
                elif not img_src.startswith('http'):
                    img_src = urljoin(source_url, img_src)
                                
                # Download and process image
                response = requests.get(img_src, timeout=10)
                response.raise_for_status()
                
                image = Image.open(BytesIO(response.content))
                
                # Extract text using OCR
                ocr_text = pytesseract.image_to_string(image)
                
                # Use direct email pattern matching
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                found_emails = re.findall(email_pattern, ocr_text, re.IGNORECASE)
                                
                for email in found_emails:
                    if self._is_valid_email_format_enhanced(email):
                        emails.append({
                            'email': email.lower(),
                            'method': 'ocr',
                            'confidence': 0.6,
                            'context': ocr_text[:200],
                            'image_src': img_src,
                            'source_url': source_url
                        })
                                                
            except Exception as e:
                logging.error(f"Error processing image {img_src}: {e}")
        
        logging.info(f"Total OCR emails found: {len(emails)}")
        return emails
    
    def extract_social_profiles(self, content: str, source_url: str) -> List[Dict]:
        """Extract social media profiles."""
        if not self.config.extract_social:
            return []
        
        profiles = []
        soup = BeautifulSoup(content, 'html.parser')
        
        # Extract from links
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            
            for platform, pattern in self.social_patterns.patterns.items():
                match = pattern.search(href)
                if match:
                    profiles.append({
                        'platform': platform,
                        'url': href,
                        'username': match.group(1) if match.groups() else None,
                        'link_text': link.get_text(strip=True),
                        'source_url': source_url
                    })
        
        return profiles
    
    def _is_valid_email_format(self, email: str) -> bool:
        """Basic email format validation."""
        if not email or len(email) < 5:
            return False
        
        # Must contain exactly one @
        if email.count('@') != 1:
            return False
        
        local, domain = email.split('@')
        
        # Basic checks
        if not local or not domain:
            return False
        
        if len(local) > 64 or len(domain) > 255:
            return False
        
        # Domain must have at least one dot
        if '.' not in domain:
            return False
        
        # Check for common invalid patterns
        invalid_patterns = [
            r'\.{2,}',  # Multiple consecutive dots
            r'^\.|\.',  # Starting or ending with dot
            r'@\.',     # @ followed by dot
            r'\.@',     # Dot followed by @
        ]
        
        for pattern in invalid_patterns:
            if re.search(pattern, email):
                return False
        
        return True
    
    def _get_context(self, text: str, start: int, end: int, context_length: int = 100) -> str:
        """Get surrounding context for an email match."""
        try:
            start_context = max(0, start - context_length)
            end_context = min(len(text), end + context_length)
            
            context = text[start_context:end_context].strip()
            # Clean up whitespace
            context = ' '.join(context.split())
            
            return context
        except Exception:
            return ""
        
    def _extract_mailto_links_enhanced(self, soup: BeautifulSoup, source_url: str) -> List[Dict]:
        """Enhanced mailto link extraction with JavaScript and obfuscation support."""
        emails = []
        
        # Method 1: Standard mailto links
        mailto_links = soup.find_all('a', href=True)
        for link in mailto_links:
            href = link.get('href', '')
            if 'mailto:' in href.lower():
                try:
                    # Extract email from mailto URL
                    if href.startswith('mailto:'):
                        email_part = href[7:]
                    else:
                        # Handle obfuscated mailto links
                        mailto_start = href.lower().find('mailto:')
                        if mailto_start != -1:
                            email_part = href[mailto_start + 7:]
                    
                    # Clean and validate
                    if '?' in email_part:
                        email_part = email_part.split('?')[0]
                    
                    email = unquote(email_part).lower().strip()
                    if self._is_valid_email_format_enhanced(email):
                        link_text = link.get_text(strip=True)
                        emails.append({
                            'email': email,
                            'method': 'mailto_link',
                            'confidence': 0.95,
                            'context': link_text,
                            'link_text': link_text,
                            'source_url': source_url
                        })
                except Exception as e:
                    logging.debug(f"Error parsing mailto link {href}: {e}")
        
        # Method 2: JavaScript-generated links
        js_emails = self._extract_js_mailto_links(soup)
        emails.extend(js_emails)
        
        # Method 3: Data attributes and onclick handlers
        data_emails = self._extract_data_attribute_emails(soup, source_url)
        emails.extend(data_emails)
        
        # Method 4: Turkish and international "Send Email" patterns
        contact_emails = self._extract_contact_form_emails(soup, source_url)
        emails.extend(contact_emails)
        
        return emails

    def _extract_js_mailto_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract emails from JavaScript-generated mailto links."""
        emails = []
        
        # Check onclick attributes
        clickable_elements = soup.find_all(attrs={'onclick': True})
        for element in clickable_elements:
            onclick = element.get('onclick', '')
            
            # Look for email patterns in onclick
            js_patterns = [
                r"mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
                r"'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'",
                r'"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"',
            ]
            
            for pattern in js_patterns:
                matches = re.findall(pattern, onclick, re.IGNORECASE)
                for email in matches:
                    if self._is_valid_email_format_enhanced(email):
                        emails.append({
                            'email': email.lower(),
                            'method': 'javascript_onclick',
                            'confidence': 0.9,
                            'context': element.get_text(strip=True),
                            'onclick_code': onclick
                        })
        
        return emails

    def _extract_data_attribute_emails(self, soup: BeautifulSoup, source_url: str) -> List[Dict]:
        """Extract emails from data attributes."""
        emails = []
        
        # Common data attribute patterns
        data_attributes = [
            'data-email', 'data-mail', 'data-contact', 'data-mailto',
            'data-user', 'data-address', 'email', 'mail'
        ]
        
        for attr in data_attributes:
            elements = soup.find_all(attrs={attr: True})
            for element in elements:
                data_value = element.get(attr, '')
                
                # Check if it's an email or encoded email
                if '@' in data_value:
                    email = data_value.lower().strip()
                    if self._is_valid_email_format_enhanced(email):
                        emails.append({
                            'email': email,
                            'method': 'data_attribute',
                            'confidence': 0.85,
                            'context': element.get_text(strip=True),
                            'attribute': attr,
                            'source_url': source_url
                        })
                
                # Try base64 decoding
                try:
                    decoded = base64.b64decode(data_value + '==').decode('utf-8', errors='ignore')
                    if '@' in decoded:
                        email = decoded.lower().strip()
                        if self._is_valid_email_format_enhanced(email):
                            emails.append({
                                'email': email,
                                'method': 'data_attribute_base64',
                                'confidence': 0.8,
                                'context': element.get_text(strip=True),
                                'attribute': attr,
                                'encoded_value': data_value,
                                'source_url': source_url
                            })
                except Exception:
                    pass
        
        return emails

    def _extract_contact_form_emails(self, soup: BeautifulSoup, source_url: str) -> List[Dict]:
        """Extract emails from contact form patterns and international text."""
        emails = []
        
        # International "Send Email" patterns
        email_trigger_texts = [
            'e-posta gönder', 'send email', 'email', 'e-mail',
            'contact', 'iletişim', 'yazışma', 'mail gönder',
            'e-posta', 'elektronik posta', 'correo', 'email enviar'
        ]
        
        # Find elements with email trigger text
        for trigger_text in email_trigger_texts:
            # Case insensitive search
            elements = soup.find_all(text=re.compile(trigger_text, re.IGNORECASE))
            
            for text_node in elements:
                parent = text_node.parent if text_node.parent else None
                if not parent:
                    continue
                
                # Check parent and nearby elements
                elements_to_check = [parent]
                elements_to_check.extend(parent.find_all())
                elements_to_check.extend(parent.find_next_siblings()[:3])
                elements_to_check.extend(parent.find_previous_siblings()[:3])
                
                for element in elements_to_check:
                    # Check href attributes
                    if hasattr(element, 'get') and element.get('href'):
                        href = element.get('href', '')
                        if 'mailto:' in href or '@' in href:
                            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', href, re.IGNORECASE)
                            if email_match:
                                email = email_match.group(1).lower()
                                if self._is_valid_email_format_enhanced(email):
                                    emails.append({
                                        'email': email,
                                        'method': 'contact_form_trigger',
                                        'confidence': 0.9,
                                        'context': f"{trigger_text}: {element.get_text(strip=True)[:100]}",
                                        'trigger_text': trigger_text,
                                        'source_url': source_url
                                    })
                    
                    # Check text content
                    element_text = element.get_text() if hasattr(element, 'get_text') else str(element)
                    email_matches = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', element_text, re.IGNORECASE)
                    for email in email_matches:
                        email = email.lower()
                        if self._is_valid_email_format_enhanced(email):
                            emails.append({
                                'email': email,
                                'method': 'contact_form_text',
                                'confidence': 0.85,
                                'context': f"{trigger_text}: {element_text[:100]}",
                                'trigger_text': trigger_text,
                                'source_url': source_url
                            })
        
        return emails
