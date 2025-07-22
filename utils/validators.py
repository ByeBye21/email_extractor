"""
Data validation utilities for emails, contacts, and URLs.
"""

import logging
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

# Optional imports with fallbacks
try:
    import validators as url_validators
    HAS_VALIDATORS = True
except ImportError:
    HAS_VALIDATORS = False

try:
    from email_validator import validate_email, EmailNotValidError
    HAS_EMAIL_VALIDATOR = True
except ImportError:
    HAS_EMAIL_VALIDATOR = False
    logging.warning("email-validator not available. Email validation will be basic.")

from utils.patterns import ValidationPatterns

def validate_url(url: str) -> bool:
    """Validate if a URL is properly formatted."""
    try:
        if HAS_VALIDATORS:
            return url_validators.url(url) is True
        else:
            # Fallback validation
            result = urlparse(url)
            return all([result.scheme, result.netloc]) and result.scheme in ['http', 'https']
    except Exception:
        return False

class DataValidator:
    """Validates and cleans extracted contact data."""

    def __init__(self, config):
        self.config = config
        self.patterns = ValidationPatterns()
        self._seen_emails: Set[str] = set()

    def validate_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """Validate and clean a list of contact records."""
        validated_contacts = []
        
        for contact in contacts:
            try:
                validated_contact = self._validate_single_contact(contact)
                if validated_contact:
                    validated_contacts.append(validated_contact)
            except Exception as e:
                logging.warning(f"Error validating contact {contact.get('email', 'unknown')}: {e}")
        
        logging.info(f"Validated {len(validated_contacts)}/{len(contacts)} contacts")
        return validated_contacts

    def _validate_single_contact(self, contact: Dict) -> Optional[Dict]:
        """Validate a single contact record."""
        # Email is required
        email = contact.get('email')
        if not email:
            return None

        # Validate email
        validated_email = self._validate_email(email)
        if not validated_email:
            return None

        # Create validated contact
        validated_contact = {
            'email': validated_email,
            'source_url': contact.get('source_url', ''),
            'extraction_method': contact.get('extraction_method', 'unknown'),
            'confidence': contact.get('confidence', 0.5),
        }

        # Validate and add optional fields
        if 'name' in contact:
            validated_name = self._validate_name(contact['name'])
            if validated_name:
                validated_contact['name'] = validated_name

        if 'phone' in contact:
            validated_phone = self._validate_phone(contact['phone'])
            if validated_phone:
                validated_contact['phone'] = validated_phone

        if 'title' in contact:
            validated_title = self._validate_title(contact['title'])
            if validated_title:
                validated_contact['title'] = validated_title

        if 'company' in contact:
            validated_company = self._validate_company(contact['company'])
            if validated_company:
                validated_contact['company'] = validated_company

        # Add metadata
        validated_contact['validation_score'] = self._calculate_validation_score(validated_contact)

        # Copy other fields
        for key, value in contact.items():
            if key not in validated_contact and value:
                validated_contact[key] = value

        return validated_contact

    def _validate_email(self, email: str) -> Optional[str]:
        """Validate and normalize an email address."""
        if not email or not isinstance(email, str):
            return None

        # Basic cleanup
        email = email.strip().lower()

        # Check for invalid patterns
        for pattern in self.patterns.invalid_email_patterns:
            if pattern.search(email):
                return None

        # Use email-validator library for thorough validation
        if self.config.validate_emails and HAS_EMAIL_VALIDATOR:
            try:
                validated = validate_email(email)
                email = validated.email
            except EmailNotValidError as e:
                logging.debug(f"Email validation failed for {email}: {e}")
                return None
        else:
            # Basic format check
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return None

        # Check for disposable email domains
        try:
            domain = email.split('@')[1]
            if domain in self.patterns.disposable_domains:
                logging.debug(f"Disposable email domain detected: {email}")
                # Don't reject, but flag it
        except IndexError:
            return None

        return email

    def _validate_name(self, name: str) -> Optional[str]:
        """Validate and clean a person's name."""
        if not name or not isinstance(name, str):
            return None

        # Clean up the name
        name = ' '.join(name.split())  # Normalize whitespace
        name = name.strip()

        # Length checks
        if len(name) < 2 or len(name) > 100:
            return None

        # Check for non-name patterns
        for pattern in self.patterns.non_name_patterns:
            if pattern.search(name):
                return None

        # Should contain mostly letters and spaces
        valid_chars = sum(1 for c in name if c.isalpha() or c.isspace() or c in "'-.")
        if valid_chars / len(name) < 0.8:
            return None

        # Capitalize properly
        name_parts = []
        for part in name.split():
            if part:
                # Handle special cases like O'Connor, McDonald
                if "'" in part:
                    subparts = part.split("'")
                    capitalized = "'".join([sp.capitalize() for sp in subparts])
                    name_parts.append(capitalized)
                elif part.lower().startswith('mc'):
                    name_parts.append('Mc' + part[2:].capitalize())
                else:
                    name_parts.append(part.capitalize())

        return ' '.join(name_parts) if name_parts else None

    def _validate_phone(self, phone: str) -> Optional[str]:
        """Validate and format a phone number."""
        if not phone or not isinstance(phone, str):
            return None

        # Remove common formatting
        cleaned = re.sub(r'[^\d+()\-\s]', '', phone)
        cleaned = cleaned.strip()

        # Length check (reasonable phone number length)
        digits_only = re.sub(r'[^\d]', '', cleaned)
        if len(digits_only) < 7 or len(digits_only) > 15:
            return None

        # Basic format validation
        phone_patterns = [
            r'^\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}$',  # US format
            r'^\+?[1-9]\d{1,14}$',  # International format
        ]

        valid_format = any(re.match(pattern, cleaned) for pattern in phone_patterns)
        if not valid_format:
            return None

        return cleaned

    def _validate_title(self, title: str) -> Optional[str]:
        """Validate and clean a job title."""
        if not title or not isinstance(title, str):
            return None

        title = ' '.join(title.split()).strip()

        # Length check
        if len(title) < 2 or len(title) > 100:
            return None

        # Should contain mostly letters, spaces, and common punctuation
        valid_chars = sum(1 for c in title if c.isalnum() or c in " -&/().")
        if valid_chars / len(title) < 0.8:
            return None

        # Capitalize properly
        # Common title words that should be lowercase
        lowercase_words = {'of', 'and', 'the', 'for', 'at', 'in', 'on', 'to', 'a', 'an'}
        words = title.split()
        capitalized_words = []

        for i, word in enumerate(words):
            if i == 0 or word.lower() not in lowercase_words:
                capitalized_words.append(word.capitalize())
            else:
                capitalized_words.append(word.lower())

        return ' '.join(capitalized_words)

    def _validate_company(self, company: str) -> Optional[str]:
        """Validate and clean a company name."""
        if not company or not isinstance(company, str):
            return None

        company = ' '.join(company.split()).strip()

        # Length check
        if len(company) < 2 or len(company) > 100:
            return None

        # Should contain mostly letters, numbers, spaces, and common punctuation
        valid_chars = sum(1 for c in company if c.isalnum() or c in " -&.,()'/")
        if valid_chars / len(company) < 0.8:
            return None

        # Capitalize properly, preserving known abbreviations
        known_abbreviations = {'LLC', 'Inc', 'Corp', 'Ltd', 'Co', 'LP', 'LLP', 'PC'}
        words = company.split()
        capitalized_words = []

        for word in words:
            if word.upper() in known_abbreviations:
                capitalized_words.append(word.upper())
            elif word.lower() in {'and', 'of', 'the', 'for'}:
                capitalized_words.append(word.lower())
            else:
                capitalized_words.append(word.capitalize())

        return ' '.join(capitalized_words)

    def _calculate_validation_score(self, contact: Dict) -> float:
        """Calculate a validation score for the contact (0.0 to 1.0)."""
        score = 0.0

        # Base score for having a valid email
        score += 0.3

        # Bonus for having additional valid fields
        if contact.get('name'):
            score += 0.2
        if contact.get('phone'):
            score += 0.2
        if contact.get('title'):
            score += 0.15
        if contact.get('company'):
            score += 0.15

        # Factor in extraction method confidence
        extraction_confidence = contact.get('confidence', 0.5)
        score *= extraction_confidence

        return min(1.0, score)

    def deduplicate_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """Remove duplicate contacts based on email address."""
        seen_emails = set()
        unique_contacts = []

        # Sort by validation score to keep the best version of duplicates
        sorted_contacts = sorted(contacts, key=lambda x: x.get('validation_score', 0), reverse=True)

        for contact in sorted_contacts:
            email = contact.get('email')
            if email and email not in seen_emails:
                seen_emails.add(email)
                unique_contacts.append(contact)

        removed_count = len(contacts) - len(unique_contacts)
        if removed_count > 0:
            logging.info(f"Removed {removed_count} duplicate contacts")

        return unique_contacts

    def validate_batch(self, contacts: List[Dict], batch_size: int = 100) -> List[Dict]:
        """Validate contacts in batches for better performance."""
        validated_contacts = []

        for i in range(0, len(contacts), batch_size):
            batch = contacts[i:i + batch_size]
            validated_batch = self.validate_contacts(batch)
            validated_contacts.extend(validated_batch)
            
            logging.debug(f"Validated batch {i//batch_size + 1}/{(len(contacts) + batch_size - 1)//batch_size}")

        return validated_contacts

    def get_validation_stats(self, original_contacts: List[Dict], validated_contacts: List[Dict]) -> Dict:
        """Get statistics about the validation process."""
        return {
            'original_count': len(original_contacts),
            'validated_count': len(validated_contacts),
            'rejection_rate': (len(original_contacts) - len(validated_contacts)) / len(original_contacts) if original_contacts else 0,
            'avg_validation_score': sum(c.get('validation_score', 0) for c in validated_contacts) / len(validated_contacts) if validated_contacts else 0,
            'with_names': sum(1 for c in validated_contacts if c.get('name')),
            'with_phones': sum(1 for c in validated_contacts if c.get('phone')),
            'with_titles': sum(1 for c in validated_contacts if c.get('title')),
            'with_companies': sum(1 for c in validated_contacts if c.get('company')),
        }
