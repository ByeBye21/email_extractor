"""
Contact Matcher - Associates emails with related contact information
Finds names, phone numbers, job titles, and company information near email addresses.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

# Optional import with fallback
try:
    import phonenumbers
    HAS_PHONENUMBERS = True
except ImportError:
    HAS_PHONENUMBERS = False
    logging.warning("phonenumbers library not available. Phone number detection will be limited.")

from utils.patterns import ContactPatterns
from utils.text_processing import TextProcessor


class ContactMatcher:
    """Matches emails with associated contact information."""
    
    def __init__(self, config):
        self.config = config
        self.patterns = ContactPatterns()
        self.text_processor = TextProcessor()
    
    def match_contacts(self, content: str, emails: List[Dict], source_url: str) -> List[Dict]:
        """
        Match emails with associated contact information.
        Returns enriched contact records.
        """
        contacts = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            text_content = self.text_processor.clean_html(content)
            
            for email_data in emails:
                email = email_data['email']
                
                # Create base contact record
                contact = {
                    'email': email,
                    'source_url': source_url,
                    'extraction_method': email_data.get('method', 'unknown'),
                    'confidence': email_data.get('confidence', 0.5),
                    'context': email_data.get('context', ''),
                }
                
                # Find associated information
                contact_info = self._find_contact_info_near_email(
                    soup, text_content, email, email_data.get('context', '')
                )
                
                # Merge contact info
                contact.update(contact_info)
                
                # Additional extraction methods
                if not contact.get('name'):
                    contact['name'] = self._extract_name_from_email(email)
                
                if not contact.get('company'):
                    contact['company'] = self._extract_company_from_domain(email)
                
                contacts.append(contact)
                
            logging.debug(f"Matched {len(contacts)} contacts from {len(emails)} emails")
            return contacts
            
        except Exception as e:
            logging.error(f"Error matching contacts: {e}")
            return [{'email': email_data['email'], 'source_url': source_url} for email_data in emails]
    
    def _find_contact_info_near_email(self, soup: BeautifulSoup, text_content: str, 
                                    email: str, context: str) -> Dict:
        """Find contact information near an email address."""
        contact_info = {}
        
        try:
            # Method 1: Look in the immediate context
            if context:
                context_info = self._extract_from_context(context)
                contact_info.update(context_info)
            
            # Method 2: Find email in DOM and look at surrounding elements
            dom_info = self._extract_from_dom_proximity(soup, email)
            self._merge_contact_info(contact_info, dom_info)
            
            # Method 3: Look for structured contact information
            structured_info = self._extract_structured_contact(soup, text_content, email)
            self._merge_contact_info(contact_info, structured_info)
            
            # Method 4: Look in contact-specific pages/sections
            if self._is_contact_page(soup, text_content):
                contact_page_info = self._extract_from_contact_page(soup, email)
                self._merge_contact_info(contact_info, contact_page_info)
            
        except Exception as e:
            logging.debug(f"Error finding contact info for {email}: {e}")
        
        return contact_info
    
    def _extract_from_context(self, context: str) -> Dict:
        """Extract contact information from email context."""
        info = {}
        
        try:
            # Extract name patterns
            name_matches = self._find_names_in_text(context)
            if name_matches:
                info['name'] = name_matches[0]  # Take the best match
            
            # Extract phone numbers
            phone_matches = self._find_phone_numbers(context)
            if phone_matches:
                info['phone'] = phone_matches[0]
            
            # Extract job titles
            title_matches = self._find_job_titles(context)
            if title_matches:
                info['title'] = title_matches[0]
            
            # Extract company names
            company_matches = self._find_company_names(context)
            if company_matches:
                info['company'] = company_matches[0]
                
        except Exception as e:
            logging.debug(f"Error extracting from context: {e}")
        
        return info
    
    def _extract_from_dom_proximity(self, soup: BeautifulSoup, email: str) -> Dict:
        """Find contact info by locating email in DOM and checking nearby elements."""
        info = {}
        
        try:
            # Find elements containing the email
            email_elements = []
            
            # Check text content of elements
            for element in soup.find_all(text=True):
                if email.lower() in element.lower():
                    parent = element.parent
                    if parent:
                        email_elements.append(parent)
            
            # Check href attributes
            for element in soup.find_all('a', href=True):
                if email.lower() in element['href'].lower():
                    email_elements.append(element)
            
            # Analyze surrounding elements
            for element in email_elements:
                # Check parent and sibling elements
                relatives = []
                
                if element.parent:
                    relatives.append(element.parent)
                    relatives.extend(element.parent.find_all())
                
                # Get siblings
                for sibling in element.find_next_siblings()[:3]:
                    relatives.append(sibling)
                for sibling in element.find_previous_siblings()[:3]:
                    relatives.append(sibling)
                
                # Extract info from relatives
                for relative in relatives:
                    text = relative.get_text(strip=True)
                    if text and len(text) < 200:  # Reasonable length
                        relative_info = self._extract_from_context(text)
                        self._merge_contact_info(info, relative_info)
                        
        except Exception as e:
            logging.debug(f"Error extracting from DOM proximity: {e}")
        
        return info
    
    def _extract_structured_contact(self, soup: BeautifulSoup, text_content: str, email: str) -> Dict:
        """Extract from structured contact sections like vCards or schema.org markup."""
        info = {}
        
        try:
            # Check for microdata/schema.org markup
            schema_info = self._extract_schema_contact(soup, email)
            self._merge_contact_info(info, schema_info)
            
            # Check for vCard-like structures
            vcard_info = self._extract_vcard_like(soup, email)
            self._merge_contact_info(info, vcard_info)
            
            # Check for common contact section patterns
            contact_sections = soup.find_all(['div', 'section', 'article'], 
                                           class_=re.compile(r'contact|team|staff|about', re.I))
            
            for section in contact_sections:
                section_text = section.get_text()
                if email.lower() in section_text.lower():
                    section_info = self._extract_from_context(section_text)
                    self._merge_contact_info(info, section_info)
                    
        except Exception as e:
            logging.debug(f"Error extracting structured contact: {e}")
        
        return info
    
    def _extract_schema_contact(self, soup: BeautifulSoup, email: str) -> Dict:
        """Extract contact info from schema.org markup."""
        info = {}
        
        try:
            # Find elements with schema.org Person markup
            person_elements = soup.find_all(attrs={'itemtype': re.compile(r'schema\.org/(Person|Employee)')})
            
            for person in person_elements:
                person_text = person.get_text()
                if email.lower() in person_text.lower():
                    # Extract structured data
                    name_elem = person.find(attrs={'itemprop': 'name'})
                    if name_elem:
                        info['name'] = name_elem.get_text(strip=True)
                    
                    title_elem = person.find(attrs={'itemprop': 'jobTitle'})
                    if title_elem:
                        info['title'] = title_elem.get_text(strip=True)
                    
                    phone_elem = person.find(attrs={'itemprop': 'telephone'})
                    if phone_elem:
                        info['phone'] = phone_elem.get_text(strip=True)
                    
                    org_elem = person.find(attrs={'itemprop': 'worksFor'})
                    if org_elem:
                        info['company'] = org_elem.get_text(strip=True)
                        
        except Exception as e:
            logging.debug(f"Error extracting schema contact: {e}")
        
        return info
    
    def _extract_vcard_like(self, soup: BeautifulSoup, email: str) -> Dict:
        """Extract from vCard-like HTML structures."""
        info = {}
        
        try:
            # Look for common vCard class patterns
            vcard_selectors = [
                '.vcard', '.hcard', '.contact-card', '.person-card',
                '.staff-member', '.team-member', '.employee-card'
            ]
            
            for selector in vcard_selectors:
                cards = soup.select(selector)
                for card in cards:
                    card_text = card.get_text()
                    if email.lower() in card_text.lower():
                        # Extract from card structure
                        card_info = self._extract_from_context(card_text)
                        self._merge_contact_info(info, card_info)
                        
                        # Look for specific vCard classes
                        name_elem = card.find(class_=re.compile(r'fn|name', re.I))
                        if name_elem:
                            info['name'] = name_elem.get_text(strip=True)
                        
                        title_elem = card.find(class_=re.compile(r'title|role|position', re.I))
                        if title_elem:
                            info['title'] = title_elem.get_text(strip=True)
                        
                        org_elem = card.find(class_=re.compile(r'org|company|organization', re.I))
                        if org_elem:
                            info['company'] = org_elem.get_text(strip=True)
                            
        except Exception as e:
            logging.debug(f"Error extracting vCard-like: {e}")
        
        return info
    
    def _extract_from_contact_page(self, soup: BeautifulSoup, email: str) -> Dict:
        """Extract enhanced info when on a contact/about page."""
        info = {}
        
        try:
            # Contact pages often have more structured information
            text_content = soup.get_text()
            
            # Look for patterns like "Name: John Doe" or "Title: Manager"
            structured_patterns = [
                (r'name\s*[:]\s*([^\n\r]{2,50})', 'name'),
                (r'title\s*[:]\s*([^\n\r]{2,50})', 'title'),
                (r'position\s*[:]\s*([^\n\r]{2,50})', 'title'),
                (r'role\s*[:]\s*([^\n\r]{2,50})', 'title'),
                (r'company\s*[:]\s*([^\n\r]{2,50})', 'company'),
                (r'organization\s*[:]\s*([^\n\r]{2,50})', 'company'),
                (r'phone\s*[:]\s*([^\n\r]{2,30})', 'phone'),
                (r'tel\s*[:]\s*([^\n\r]{2,30})', 'phone'),
            ]
            
            for pattern, field in structured_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE)
                if matches:
                    info[field] = matches[0].strip()
                    
        except Exception as e:
            logging.debug(f"Error extracting from contact page: {e}")
        
        return info
    
    def _find_names_in_text(self, text: str) -> List[str]:
        """Find person names in text."""
        names = []
        
        try:
            # Use name patterns
            for pattern in self.patterns.name_patterns:
                matches = pattern.findall(text)
                for match in matches:
                    name = ' '.join(match) if isinstance(match, tuple) else match
                    name = name.strip()
                    
                    # Basic name validation
                    if self._is_valid_name(name):
                        names.append(name)
                        
        except Exception as e:
            logging.debug(f"Error finding names: {e}")
        
        return names
    
    def _find_phone_numbers(self, text: str) -> List[str]:
        """Find and format phone numbers."""
        phones = []
        
        try:
            # Use phonenumbers library for better accuracy if available
            if HAS_PHONENUMBERS:
                for match in phonenumbers.PhoneNumberMatcher(text, None):
                    phone = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                    phones.append(phone)
            
            # Fallback to regex patterns
            if not phones:
                for pattern in self.patterns.phone_patterns:
                    matches = pattern.findall(text)
                    phones.extend(matches)
                    
        except Exception as e:
            logging.debug(f"Error finding phones: {e}")
        
        return phones
    
    def _find_job_titles(self, text: str) -> List[str]:
        """Find job titles in text."""
        titles = []
        
        try:
            for pattern in self.patterns.job_title_patterns:
                matches = pattern.findall(text)
                for match in matches:
                    title = match.strip()
                    if self._is_valid_job_title(title):
                        titles.append(title)
                        
        except Exception as e:
            logging.debug(f"Error finding job titles: {e}")
        
        return titles
    
    def _find_company_names(self, text: str) -> List[str]:
        """Find company names in text."""
        companies = []
        
        try:
            for pattern in self.patterns.company_patterns:
                matches = pattern.findall(text)
                for match in matches:
                    company = match.strip()
                    if self._is_valid_company_name(company):
                        companies.append(company)
                        
        except Exception as e:
            logging.debug(f"Error finding company names: {e}")
        
        return companies
    
    def _extract_name_from_email(self, email: str) -> Optional[str]:
        """Extract a possible name from email address."""
        try:
            local_part = email.split('@')[0]
            
            # Common patterns: first.last, firstname.lastname
            if '.' in local_part:
                parts = local_part.split('.')
                if len(parts) == 2:
                    first, last = parts
                    # Basic cleanup
                    first = re.sub(r'[^a-zA-Z]', '', first).capitalize()
                    last = re.sub(r'[^a-zA-Z]', '', last).capitalize()
                    
                    if len(first) > 1 and len(last) > 1:
                        return f"{first} {last}"
            
            # Single name
            name = re.sub(r'[^a-zA-Z]', '', local_part).capitalize()
            if len(name) > 2:
                return name
                
        except Exception:
            pass
        
        return None
    
    def _extract_company_from_domain(self, email: str) -> Optional[str]:
        """Extract company name from email domain."""
        try:
            domain = email.split('@')[1].lower()
            
            # Remove common subdomains
            domain_parts = domain.split('.')
            if len(domain_parts) > 2:
                # Keep the main domain part
                if domain_parts[-2] not in ['co', 'com', 'net', 'org']:
                    company = domain_parts[-2]
                else:
                    company = domain_parts[-3] if len(domain_parts) > 2 else domain_parts[-2]
            else:
                company = domain_parts[0]
            
            # Capitalize and clean
            company = company.replace('-', ' ').replace('_', ' ')
            company = ' '.join(word.capitalize() for word in company.split())
            
            return company
            
        except Exception:
            return None
    
    def _is_contact_page(self, soup: BeautifulSoup, text_content: str) -> bool:
        """Determine if this appears to be a contact page."""
        # Check title
        title = soup.find('title')
        if title and re.search(r'contact|about|team|staff', title.get_text(), re.I):
            return True
        
        # Check URL patterns (would need URL passed in)
        # Check page content
        contact_indicators = ['contact us', 'get in touch', 'our team', 'staff directory']
        text_lower = text_content.lower()
        
        return any(indicator in text_lower for indicator in contact_indicators)
    
    def _merge_contact_info(self, target: Dict, source: Dict) -> None:
        """Merge contact info, preferring existing values."""
        for key, value in source.items():
            if key not in target and value:
                target[key] = value
    
    def _is_valid_name(self, name: str) -> bool:
        """Validate if string looks like a person name."""
        if not name or len(name) < 2 or len(name) > 100:
            return False
        
        # Should contain mostly letters
        letter_ratio = sum(c.isalpha() for c in name) / len(name)
        if letter_ratio < 0.7:
            return False
        
        # Avoid common false positives
        invalid_names = [
            'email', 'contact', 'info', 'admin', 'webmaster', 'support',
            'sales', 'marketing', 'hr', 'privacy', 'legal'
        ]
        
        return name.lower() not in invalid_names
    
    def extract_academic_info(self, text: str, email: str) -> Dict[str, str]:
        """Extract academic titles and full names from university pages."""
        
        # English academic titles
        titles = [
            r'Professor\s+Dr\.?',
            r'Prof\.?\s+Dr\.?',
            r'Associate\s+Professor',
            r'Assistant\s+Professor',
            r'Dr\.?\s+',
            r'PhD\.?',
            r'Research\s+Fellow',
            r'Lecturer',
            r'Senior\s+Lecturer',
            r'Director',
            r'Dean'
        ]
        
        # Find email context in text
        email_prefix = re.escape(email.split('@')[0])
        
        # Pattern to find title + name near email
        context_pattern = rf'({"|".join(titles)})?\s*([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)\s*.*?{email_prefix}'
        
        match = re.search(context_pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return {
                'title': match.group(1).strip() if match.group(1) else '',
                'name': match.group(2).strip()
            }
        
        # Reverse pattern: email first, then title and name
        reverse_pattern = rf'{email_prefix}\s*.*?({"|".join(titles)})?\s*([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)'
        
        match = re.search(reverse_pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return {
                'title': match.group(1).strip() if match.group(1) else '',
                'name': match.group(2).strip()
            }
        
        return {'title': '', 'name': ''}