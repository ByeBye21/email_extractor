"""
Website Crawler - Core crawling orchestration
Handles the main crawling logic, respects robots.txt, and manages crawl state.
"""

import asyncio
import logging
import time
import re
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
import spacy
from typing import Dict, List

# Optional imports with fallbacks
try:
    from playwright.async_api import async_playwright, Browser, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    logging.warning("Playwright not available. JavaScript rendering disabled.")

try:
    from asyncio_throttle import Throttler
    HAS_THROTTLER = True
except ImportError:
    HAS_THROTTLER = False
    logging.warning("asyncio-throttle not available. Basic rate limiting will be used.")

from extractors.email_extractor import EmailExtractor
from extractors.contact_matcher import ContactMatcher
from utils.config import Config
from utils.exporters import ResultExporter
from utils.validators import DataValidator
from utils.progress_tracker import ProgressTracker


class CrawlResult:
    """Represents the result of crawling a single page."""
    
    def __init__(self, url: str, emails: List[Dict], contacts: List[Dict], 
                 social_profiles: List[Dict] = None):
        self.url = url
        self.emails = emails or []
        self.contacts = contacts or []
        self.social_profiles = social_profiles or []
        self.timestamp = time.time()


class WebsiteCrawler:
    """Main website crawler that orchestrates the crawling process."""
    
    def __init__(self, config: Config):
        self.config = config
        self.email_extractor = EmailExtractor(config)
        self.contact_matcher = ContactMatcher(config)
        self.validator = DataValidator(config)
        self.exporter = ResultExporter(config)
        self.progress_tracker = ProgressTracker()
        
        # Crawl state
        self.visited_urls: Set[str] = set()
        self.queued_urls: Set[str] = set()
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.failed_urls: Dict[str, str] = {}  # URL -> error reason
        
        # Rate limiting
        if HAS_THROTTLER:
            self.throttler = Throttler(rate_limit=1/config.delay)
        else:
            self.throttler = None
        
        # Browser for JavaScript rendering
        self.browser: Optional[Browser] = None
        self.playwright = None

        # Load spaCy model
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logging.info("spaCy NLP model loaded successfully")
        except OSError:
            logging.warning("spaCy model not found, falling back to regex patterns")
            self.nlp = None
        
        logging.info(f"WebsiteCrawler initialized with config: {config}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self.config.use_javascript and HAS_PLAYWRIGHT:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def _get_robots_parser(self, base_url: str) -> Optional[RobotFileParser]:
        """Get or create a robots.txt parser for the domain."""
        domain = urlparse(base_url).netloc
        
        if domain not in self.robots_cache:
            try:
                robots_url = urljoin(base_url, '/robots.txt')
                rp = RobotFileParser()
                rp.set_url(robots_url)
                rp.read()
                self.robots_cache[domain] = rp
                logging.debug(f"Loaded robots.txt for {domain}")
            except Exception as e:
                logging.warning(f"Could not load robots.txt for {domain}: {e}")
                self.robots_cache[domain] = None
        
        return self.robots_cache[domain]
    
    def _can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        try:
            rp = self._get_robots_parser(url)
            if rp:
                return rp.can_fetch(self.config.user_agent, url)
            return True  # Allow if no robots.txt
        except Exception as e:
            logging.warning(f"Error checking robots.txt for {url}: {e}")
            return True  # Allow on error
    
    def _should_crawl_url(self, url: str, base_domain: str, current_depth: int) -> bool:
        """Determine if a URL should be crawled."""
        try:
            parsed = urlparse(url)
            
            # Check depth limit
            if current_depth >= self.config.max_depth:
                return False
            
            # Check if already visited
            if url in self.visited_urls or url in self.queued_urls:
                return False
            
            # Check domain restrictions
            if self.config.allowed_domains:
                if parsed.netloc not in self.config.allowed_domains:
                    return False
            
            if self.config.excluded_domains:
                if parsed.netloc in self.config.excluded_domains:
                    return False
            
            # Stay within same domain by default
            if parsed.netloc != base_domain:
                return False
            
            # Check file extensions
            path = parsed.path.lower()
            if any(path.endswith(ext) for ext in self.config.excluded_extensions):
                return False
            
            # Check robots.txt
            if not self._can_fetch(url):
                return False
            
            # Avoid query parameters that might cause infinite loops
            if parsed.query:
                query_params = parse_qs(parsed.query)
                # Skip pagination with large page numbers
                if 'page' in query_params:
                    try:
                        page_num = int(query_params['page'][0])
                        if page_num > 100:  # Reasonable limit
                            return False
                    except (ValueError, IndexError):
                        pass
            
            return True
            
        except Exception as e:
            logging.warning(f"Error checking URL {url}: {e}")
            return False
    
    def _extract_links(self, content: str, base_url: str) -> List[str]:
        """Extract all links from HTML content."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            links = []
            
            # Find all anchor tags with href
            for link in soup.find_all('a', href=True):
                href = link['href'].strip()
                if href:
                    absolute_url = urljoin(base_url, href)
                    # Remove fragment identifier
                    absolute_url = absolute_url.split('#')[0]
                    links.append(absolute_url)
            
            return links
            
        except Exception as e:
            logging.warning(f"Error extracting links from {base_url}: {e}")
            return []
    
    async def _fetch_page_content(self, url: str) -> Optional[str]:
        """Fetch page content, with optional JavaScript rendering."""
        try:
            if self.throttler:
                async with self.throttler:
                    if self.config.use_javascript and self.browser:
                        return await self._fetch_with_playwright(url)
                    else:
                        return await self._fetch_with_httpx(url)
            else:
                # Basic rate limiting without throttler
                await asyncio.sleep(self.config.delay)
                if self.config.use_javascript and self.browser:
                    return await self._fetch_with_playwright(url)
                else:
                    return await self._fetch_with_httpx(url)
        except Exception as e:
            logging.error(f"Failed to fetch {url}: {e}")
            self.failed_urls[url] = str(e)
            return None
    
    async def _fetch_with_httpx(self, url: str) -> Optional[str]:
        """Fetch page content using httpx."""
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={'User-Agent': self.config.user_agent},
            follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    
    async def _fetch_with_playwright(self, url: str) -> Optional[str]:
        """Enhanced Playwright fetching with better JavaScript execution."""
        page: Page = await self.browser.new_page()
        try:
            # Navigate and wait for content
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Execute any pending JavaScript
            await page.wait_for_timeout(2000)  # Wait 2 seconds for JS to execute
            
            # Try to trigger any email-related JavaScript
            try:
                # Look for common email trigger elements and hover over them
                email_triggers = await page.query_selector_all('a[onclick*="mail"], a[onclick*="email"], .email-link, .contact-email')
                for trigger in email_triggers[:5]:  # Limit to first 5
                    try:
                        await trigger.hover()
                        await page.wait_for_timeout(500)
                    except:
                        pass
            except:
                pass
            
            # Get final content after JavaScript execution
            content = await page.content()
            return content
            
        finally:
            await page.close()
    
    async def _crawl_single_page(self, url: str, depth: int) -> Optional[CrawlResult]:
        """Single page crawling"""
        try:
            logging.info(f"Crawling (depth {depth}): {url}")
            
            # Fetch page content
            content = await self._fetch_page_content(url)
            if not content:
                return None
            
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            
            # Try structured extraction first
            emails = self.extract_emails_with_context(soup, url)
            
            if not emails:
                # Fallback to standard extraction
                emails = self.email_extractor.extract_emails(content, url)
                # Apply enhancements
                emails = self.enhance_extracted_data(emails, url)
            
            # Convert emails to contacts format
            contacts = []
            for email_data in emails:
                contact = {
                    'email': email_data.get('email'),
                    'name': email_data.get('name', ''),
                    'title': email_data.get('title', ''),
                    'company': email_data.get('company', ''),
                    'phone': email_data.get('phone', ''),
                    'source_url': url,
                    'extraction_method': email_data.get('method', 'unknown'),
                    'confidence': email_data.get('confidence', 0.5),
                    'validation_score': self._calculate_validation_score(email_data.get('email', '')),
                    'context': email_data.get('context', '')
                }
                contacts.append(contact)
            
            # Extract social profiles if enabled
            social_profiles = []
            if self.config.extract_social:
                social_profiles = self.email_extractor.extract_social_profiles(content, url)
            
            # Update progress
            self.progress_tracker.update_progress(url, len(emails), len(contacts))
            
            return CrawlResult(url, emails, contacts, social_profiles)
            
        except Exception as e:
            logging.error(f"Error crawling {url}: {e}")
            self.failed_urls[url] = str(e)
            return None
    
    async def crawl_website(self, start_url: str) -> List[Dict]:
        """Crawl an entire website starting from the given URL."""
        async with self: # Use context manager for browser lifecycle
            try:
                base_domain = urlparse(start_url).netloc
                logging.info(f"Starting crawl of {start_url} (domain: {base_domain})")
                
                # Initialize crawl queue
                self.queued_urls.add(start_url)
                all_results = []
                current_depth = 0
                
                while (self.queued_urls and current_depth < self.config.max_depth and 
                    len(self.visited_urls) < self.config.max_pages):
                    
                    # Get URLs for current depth
                    current_urls = list(self.queued_urls)
                    self.queued_urls.clear()
                    
                    # Enforce max_pages limit
                    remaining_pages = self.config.max_pages - len(self.visited_urls)
                    if remaining_pages <= 0:
                        break
                    
                    if len(current_urls) > remaining_pages:
                        current_urls = current_urls[:remaining_pages]
                    
                    next_urls = set()
                    batch_size = min(20, len(current_urls))
                    
                    for i in range(0, len(current_urls), batch_size):
                        batch = current_urls[i:i + batch_size]
                        
                        # Crawl batch concurrently
                        tasks = [self._crawl_single_page(url, current_depth) for url in batch]
                        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                        
                        # Process results
                        for url, result in zip(batch, batch_results):
                            self.visited_urls.add(url)
                            if isinstance(result, CrawlResult):
                                all_results.append(result)
                                
                                # Extract links for next depth
                                if current_depth < self.config.max_depth - 1:
                                    page_content = await self._fetch_page_content(url)
                                    if page_content:
                                        links = self._extract_links(page_content, url)
                                        for link in links:
                                            if self._should_crawl_url(link, base_domain, current_depth + 1):
                                                next_urls.add(link)
                            
                            if len(self.visited_urls) >= self.config.max_pages:
                                break
                        
                        if len(self.visited_urls) >= self.config.max_pages:
                            break
                    
                    # Add discovered URLs to queue for next depth
                    self.queued_urls.update(next_urls)
                    current_depth += 1
                
                # Process and export results
                return await self._process_results(all_results, start_url)
                
            except Exception as e:
                logging.error(f"Error during website crawl: {e}")
                raise

    def extract_emails_with_context(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract emails with full context."""
        
        emails_found = []
        
        # Method 1: Enhanced mailto links with context
        mailto_links = soup.find_all('a', href=re.compile(r'mailto:', re.I))
        for link in mailto_links:
            try:
                href = link.get('href', '')
                email_match = re.search(r'mailto:([^?&\s]+)', href)
                if email_match:
                    email = email_match.group(1).lower().strip()
                    
                    if self._is_valid_email_format_enhanced(email):
                        # Extract context around this email
                        context_info = self._extract_context_around_element(link, email, url)
                        
                        emails_found.append({
                            'email': email,
                            'name': context_info.get('name', ''),
                            'title': context_info.get('title', ''),
                            'company': context_info.get('company', ''),
                            'phone': context_info.get('phone', ''),
                            'source_url': url,
                            'method': 'mailto_enhanced',
                            'confidence': 0.9,
                            'context': context_info.get('context', '')
                        })
            except Exception as e:
                logging.debug(f"Error processing mailto link: {e}")
        
        # Method 2: Extract from structured content (tables, lists, cards)
        structured_emails = self._extract_from_structured_content(soup, url)
        emails_found.extend(structured_emails)
        
        # Method 3: Extract from general text patterns
        text_emails = self._extract_from_text_patterns(soup, url)
        emails_found.extend(text_emails)
        
        # Remove duplicates and enhance
        unique_emails = self._remove_duplicates(emails_found)
        
        return unique_emails

    def _extract_context_around_element(self, element, email: str, url: str) -> Dict:
        """GENERAL PURPOSE: Extract name, title, company from HTML structure - STRICT validation."""
        
        name = ""
        title = ""
        company = ""
        phone = ""
        context_text = ""
        
        # Method 1: Look for structured HTML elements (UNIVERSAL)
        parent_container = element
        for level in range(5):  # Check 5 levels up
            if parent_container and parent_container.parent:
                parent_container = parent_container.parent
                
                # Look for common name/title patterns in ANY language
                name_title_elem = self._find_name_title_element(parent_container)
                
                if name_title_elem:
                    full_text = name_title_elem.get_text(strip=True)
                    context_text = full_text
                    
                    # Extract from structured text
                    extracted = self._parse_universal_title_name(full_text, full_text)
                    if extracted['name']:
                        name = extracted['name']
                        title = extracted['title']
                        break
                
                if name:  # Found good match, stop searching
                    break
        
        # Method 2: Fallback to context text parsing
        if not name:
            for level in range(3):
                if element and element.parent:
                    element = element.parent
                    level_text = element.get_text(separator=' ', strip=True)
                    if len(level_text) > len(context_text) and len(level_text) < 500:
                        context_text = level_text
            
            if context_text:
                # Use AI or regex on text
                if self.nlp:
                    extracted_info = self._parse_context_with_ai(context_text, email)
                else:
                    extracted_info = self._parse_context_with_regex_strict(context_text, email)
                
                name = extracted_info.get('name', '')
                title = extracted_info.get('title', '')
                company = extracted_info.get('company', '')
                phone = extracted_info.get('phone', '')
        
        # STRICT VALIDATION - Only return if very confident
        name = self._clean_universal_name(name) if name else ''
        title = title if self._is_confident_title(title) else ''
        company = company if self._is_confident_company(company) else ''
        
        # Additional strict validation
        if name and not self._is_confident_name(name):
            name = ''
        
        return {
            'name': name,
            'title': title,
            'company': company,
            'phone': phone,
            'context': context_text[:300]
        }


    def _extract_from_structured_content(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract from tables, lists, and card layouts."""
        
        emails = []
        
        # Extract from tables
        tables = soup.find_all('table')
        for table in tables:
            emails.extend(self._extract_from_table(table, url))
        
        # Extract from lists
        lists = soup.find_all(['ul', 'ol'])
        for list_elem in lists:
            emails.extend(self._extract_from_list(list_elem, url))
        
        # Extract from card/profile layouts
        cards = soup.find_all(['div', 'article'], class_=re.compile(r'(card|profile|member|staff|person|contact)', re.I))
        for card in cards:
            emails.extend(self._extract_from_card(card, url))
        
        return emails

    def _extract_from_table(self, table, url: str) -> List[Dict]:
        """Extract emails from table structure."""
        emails = []
        
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_text = ' '.join([cell.get_text(strip=True) for cell in cells])
            
            # Find emails in this row
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            found_emails = re.findall(email_pattern, row_text)
            
            for email in found_emails:
                if self._is_valid_email_format_enhanced(email.lower()):
                    info = self._parse_context_text(row_text, email)
                    emails.append({
                        'email': email.lower(),
                        'name': info.get('name', ''),
                        'title': info.get('title', ''),
                        'company': info.get('company', ''),
                        'phone': info.get('phone', ''),
                        'source_url': url,
                        'method': 'table_structure',
                        'confidence': 0.9,
                        'context': row_text[:200]
                    })
        
        return emails

    def _extract_from_list(self, list_elem, url: str) -> List[Dict]:
        """Extract emails from list structure."""
        emails = []
        
        items = list_elem.find_all('li')
        for item in items:
            item_text = item.get_text(strip=True)
            
            # Find emails in this item
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            found_emails = re.findall(email_pattern, item_text)
            
            for email in found_emails:
                if self._is_valid_email_format_enhanced(email.lower()):
                    info = self._parse_context_text(item_text, email)
                    emails.append({
                        'email': email.lower(),
                        'name': info.get('name', ''),
                        'title': info.get('title', ''),
                        'company': info.get('company', ''),
                        'phone': info.get('phone', ''),
                        'source_url': url,
                        'method': 'list_structure',
                        'confidence': 0.85,
                        'context': item_text[:200]
                    })
        
        return emails

    def _extract_from_card(self, card, url: str) -> List[Dict]:
        """Extract emails from card/profile layouts"""
        emails = []
        
        card_text = card.get_text(separator=' ', strip=True)
        
        # Find emails in this card
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found_emails = re.findall(email_pattern, card_text)
        
        for email in found_emails:
            if self._is_valid_email_format_enhanced(email.lower()):
                # DON'T extract info from mixed card text - use email only
                name = ''  # Leave blank - don't guess
                title = ''  # Leave blank - don't guess
                company = ''  # Leave blank - don't guess
                
                emails.append({
                    'email': email.lower(),
                    'name': name,
                    'title': title,
                    'company': company,
                    'phone': '',
                    'source_url': url,
                    'method': 'card_structure_strict',
                    'confidence': 0.75,  # Lower confidence since we're not extracting context
                    'context': card_text[:100]  # Shorter context
                })
        
        return emails


    def _extract_from_text_patterns(self, soup: BeautifulSoup, url: str) -> List[Dict]:
        """Extract emails from general text patterns."""
        emails = []
        
        # Get all text content
        all_text = soup.get_text(separator=' ')
        
        # Find all emails in text
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        found_emails = re.findall(email_pattern, all_text)
        
        for email in found_emails:
            if self._is_valid_email_format_enhanced(email.lower()):
                # Find context around each email
                email_pos = all_text.find(email)
                if email_pos != -1:
                    start = max(0, email_pos - 150)
                    end = min(len(all_text), email_pos + len(email) + 150)
                    context = all_text[start:end].strip()
                    
                    info = self._parse_context_text(context, email)
                    emails.append({
                        'email': email.lower(),
                        'name': info.get('name', ''),
                        'title': info.get('title', ''),
                        'company': info.get('company', ''),
                        'phone': info.get('phone', ''),
                        'source_url': url,
                        'method': 'text_pattern',
                        'confidence': 0.75,
                        'context': context
                    })
        
        return emails

    def _parse_context_text(self, text: str, email: str) -> Dict:
            """AI-powered context parsing using spaCy NER."""
            
            # Try AI extraction first
            if self.nlp:
                ai_result = self._parse_context_with_ai(text, email)
                if ai_result.get('name') and len(ai_result['name']) > 3:
                    return ai_result
            
            # Fallback to enhanced regex extraction
            return self._parse_context_with_regex(text, email)
    
    def _parse_context_with_ai(self, text: str, email: str) -> Dict:
        """Use spaCy NER for intelligent extraction - STRICT validation."""
        
        try:
            # Process text with spaCy
            doc = self.nlp(text)
            
            # Extract persons (names) - be more selective
            persons = []
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    clean_name = self._clean_ai_extracted_name(ent.text, email)
                    if clean_name and self._validate_ai_name_strict(clean_name, email):
                        persons.append(clean_name)
            
            # Extract organizations - be more selective
            organizations = []
            for ent in doc.ents:
                if ent.label_ == "ORG" and self._is_valid_organization(ent.text):
                    organizations.append(ent.text)
            
            # Get best matches - only if confident
            name = self._select_best_ai_name(persons, email) if persons else ''
            company = self._select_best_organization(organizations) if organizations else ''
            
            # Extract title - only if confident
            title = self._extract_title_strict(text, doc)
            
            # Extract phone
            phone = self._extract_phone_number_ai(text)
            
            # STRICT VALIDATION - don't use fallbacks unless very confident
            if not name or not self._is_confident_name(name):
                name = ''  # Leave blank instead of email fallback
            
            if not company or not self._is_confident_company(company):
                company = ''  # Leave blank
            
            if not title or not self._is_confident_title(title):
                title = ''  # Leave blank
            
            return {
                'name': name,
                'title': title,
                'company': company,
                'phone': phone
            }
            
        except Exception as e:
            logging.debug(f"AI extraction failed: {e}")
            return self._parse_context_with_regex_strict(text, email)

    
    def _clean_ai_extracted_name(self, name: str, email: str) -> str:
        """Clean AI-extracted name from noise."""
        
        # Remove common non-name words
        noise_words = {
            'department', 'university', 'college', 'prof', 'dr', 'email',
            'computer', 'engineering', 'science', 'faculty', 'staff',
            'institute', 'school', 'center', 'office', 'building'
        }
        
        words = name.split()
        clean_words = []
        
        for word in words:
            if word.lower() not in noise_words and len(word) > 1:
                clean_words.append(word)
        
        return ' '.join(clean_words) if len(clean_words) >= 2 else ''
    
    def _validate_ai_name(self, name: str, email: str) -> bool:
        """Validate if AI-extracted name matches email pattern."""
        
        if not name or len(name.split()) < 2:
            return False
        
        email_username = email.split('@')[0].lower()
        name_parts = [part.lower() for part in name.split()]
        
        # Check if any name part appears in email
        for part in name_parts:
            if len(part) > 2 and part in email_username:
                return True
        
        # Check if email contains initials
        initials = ''.join([part[0].lower() for part in name_parts])
        if len(initials) >= 2 and initials in email_username:
            return True
        
        return False
    
    def _select_best_ai_name(self, names: List[str], email: str) -> str:
        """Select the best name from AI candidates."""
        
        if not names:
            return ''
        
        # Score names based on email match
        scored_names = []
        for name in names:
            score = self._calculate_ai_name_score(name, email)
            scored_names.append((score, name))
        
        # Return highest scoring name
        scored_names.sort(reverse=True)
        return scored_names[0][1] if scored_names[0][0] > 0 else names[0]
    
    def _calculate_ai_name_score(self, name: str, email: str) -> float:
        """Calculate how well an AI-extracted name matches an email."""
        
        email_username = email.split('@')[0].lower()
        name_lower = name.lower().replace(' ', '')
        
        score = 0.0
        
        # Direct substring match
        if name_lower in email_username or email_username in name_lower:
            score += 1.0
        
        # Word matches
        name_words = name.lower().split()
        for word in name_words:
            if len(word) > 2 and word in email_username:
                score += 0.5
        
        # Initial match
        if len(name_words) >= 2:
            initials = ''.join([w[0] for w in name_words])
            if initials in email_username:
                score += 0.3
        
        return score
    
    def _extract_title_ai_enhanced(self, text: str, doc) -> str:
        """Extract title using both spaCy and patterns."""
        
        # First try pattern matching for academic titles
        academic_patterns = [
            r'Professor',
            r'Prof\.?',
            r'Associate Professor',
            r'Assistant Professor',
            r'Dr\.?',
            r'PhD',
            r'Director',
            r'Manager',
            r'Engineer',
            r'Analyst',
            r'Lecturer',
            r'Research Assistant',
            r'Senior\s+\w+',
            r'Lead\s+\w+'
        ]
        
        for pattern in academic_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        
        # Try to find job titles using spaCy entities
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG"]:
                # Look around the entity for title words
                start_idx = max(0, ent.start - 3)
                end_idx = min(len(doc), ent.end + 3)
                context_tokens = doc[start_idx:end_idx]
                
                for token in context_tokens:
                    if token.text.lower() in ['professor', 'director', 'manager', 'engineer', 'analyst']:
                        return token.text.title()
        
        return ''
    
    def _extract_phone_number_ai(self, text: str) -> str:
        """Extract complete phone numbers - UNIVERSAL patterns only."""
        
        phone_patterns = [
            # International format with extensions
            r'\+\d{1,3}\s*\(\d{3}\)\s*\d{3}\s*\d{2}\s*\d{2}(?:\s*/\s*\d{3,4})?',
            # Standard international
            r'\+\d{1,3}\s*\d{3}\s*\d{3}\s*\d{2}\s*\d{2}',
            # US format
            r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}',
            # General complete format
            r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}'
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(0).strip()
                # Only return if complete (10+ digits)
                if len(re.sub(r'[^\d]', '', phone)) >= 10:
                    return phone
        
        return ''

    def _parse_context_with_regex(self, text: str, email: str) -> Dict:
        """Fallback regex-based context parsing (your existing method)."""
        
        # Clean text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Extract phone numbers
        phone_pattern = r'[\+]?[1-9]?[\d\s\-\(\)\.]{10,15}'
        phones = re.findall(phone_pattern, text)
        phone = phones[0].strip() if phones else ''
        
        # Extract names with patterns for academic context
        name = ''
        
        # General academic title patterns
        title_name_patterns = [
            r'(?:Professor|Prof\.?|Associate Professor|Assistant Professor|Dr\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            r'(?:Director|Manager|Engineer|Analyst)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
        ]

        for pattern in title_name_patterns:
            matches = re.findall(pattern, text)
            if matches:
                candidate = matches[0].strip()
                # Filter out department words
                if not any(word in candidate.lower() for word in ['department', 'engineering', 'science']):
                    if len(candidate.split()) >= 2:
                        name = candidate
                        break
        
        # If no title-based match, use email inference
        if not name:
            name = self.infer_name_from_email(email)
        
        # Extract titles
        title_patterns = [
            r'\b(Professor|Prof\.?)\b',
            r'\b(Associate Professor)\b', 
            r'\b(Assistant Professor)\b',
            r'\b(Director)\b',
            r'\b(Manager)\b',
            r'\b(Engineer)\b',
            r'\b(Lecturer)\b',
            r'\b(Research Assistant)\b',
            r'\b(Dr\.?|PhD|Ph\.D\.?)\b',
            r'\b(Senior\s+\w+)\b',
            r'\b(Lead\s+\w+)\b'
        ]
        
        title = ''
        for pattern in title_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                title = matches[0]
                break
        
        # Extract company/organization
        company_patterns = [
            r'\b(University|College|School)\s+of\s+\w+\b',
            r'\b\w+\s+(University|College|Institute|Corporation|Corp|Inc|LLC|Ltd)\b'
        ]
        
        company = ''
        for pattern in company_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                company = matches[0]
                break
        
        if not company:
            company = self._infer_company_from_domain(email.split('@')[1], "")
        
        return {
            'name': name,
            'title': title, 
            'company': company,
            'phone': phone
        }
    
    def _validate_ai_name_strict(self, name: str, email: str) -> bool:
        """STRICT validation for AI-extracted names."""
        
        if not name or len(name.split()) < 2:
            return False
        
        # Each word must be properly formatted
        words = name.split()
        for word in words:
            if not (word[0].isupper() and word[1:].islower() and word.isalpha() and len(word) >= 2):
                return False
        
        # Must have strong email correlation
        email_username = email.split('@')[0].lower()
        name_parts = [part.lower() for part in words]
        
        # Require at least one strong match
        strong_match = False
        for part in name_parts:
            if len(part) >= 3 and part in email_username:
                strong_match = True
                break
        
        return strong_match

    def _is_confident_name(self, name: str) -> bool:
        """UNIVERSAL name validation - any language."""
        
        if not name or len(name.strip()) < 3:
            return False
        
        name = name.strip()
        words = name.split()
        
        # Must have 2-4 words
        if len(words) < 2 or len(words) > 4:
            return False
        
        # Universal non-name words (English only)
        non_name_indicators = [
            'consultation', 'info', 'contact', 'admin', 'support',
            'department', 'faculty', 'office', 'secretary', 'email',
            'phone', 'address', 'university', 'college'
        ]
        
        name_lower = name.lower()
        for indicator in non_name_indicators:
            if indicator in name_lower:
                return False
        
        # Each word must start with capital letter and be alphabetic
        for word in words:
            if not (len(word) >= 2 and word[0].isupper() and word.isalpha()):
                return False
        
        return True

    def _is_confident_title(self, title: str) -> bool:
        """STRICT title validation - only accept well-known titles."""
        
        if not title or len(title.strip()) < 2:
            return False
        
        # Only these exact titles are acceptable
        confident_titles = {
            'professor', 'prof', 'prof.', 'associate professor', 'assistant professor',
            'dr', 'dr.', 'director', 'manager', 'head', 'dean', 'chair', 'lecturer'
        }
        
        return title.lower().strip() in confident_titles

    def _is_confident_company(self, company: str) -> bool:
        """STRICT company validation."""
        
        if not company or len(company.strip()) < 3:
            return False
        
        # Must contain organizational indicators
        org_indicators = ['university', 'college', 'institute', 'corporation', 'company', 'inc', 'ltd', 'llc']
        
        return any(indicator in company.lower() for indicator in org_indicators)

    def _is_valid_organization(self, org: str) -> bool:
        """Validate if extracted organization is real."""
        
        if not org or len(org.strip()) < 5:
            return False
        
        # Skip obvious non-organizations
        skip_words = ['email', 'contact', 'phone', 'address', 'website']
        if any(word in org.lower() for word in skip_words):
            return False
        
        return True

    def _extract_title_strict(self, text: str, doc) -> str:
        """Extract title with strict validation."""
        
        # Only look for very specific academic/professional titles
        strict_patterns = [
            r'\b(Professor)\b',
            r'\b(Associate Professor)\b',
            r'\b(Assistant Professor)\b', 
            r'\b(Dr\.)\b',
            r'\b(Director)\b',
            r'\b(Manager)\b',
            r'\b(Dean)\b',
            r'\b(Chair)\b'
        ]
        
        for pattern in strict_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ''  # Return empty if no clear match

    def _select_best_organization(self, organizations: List[str]) -> str:
        """Select best organization from candidates."""
        
        if not organizations:
            return ''
        
        # Prefer educational institutions
        for org in organizations:
            if any(word in org.lower() for word in ['university', 'college', 'institute']):
                return org
        
        # Return first valid one
        return organizations[0] if organizations else ''

    def _clean_email_format(self, email: str) -> str:
        """Clean email format - UNIVERSAL validation."""
        
        if not email:
            return ""
        
        email = email.strip().lower()
        
        # Basic email validation pattern
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(email_pattern, email):
            return email
        
        return ""

    def _parse_context_with_regex_strict(self, text: str, email: str) -> Dict:
        """STRICT regex-based context parsing."""
        
        # Clean text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Extract phone numbers
        phone_pattern = r'[\+]?[\d\s\-\(\)\.]{10,15}'
        phones = re.findall(phone_pattern, text)
        phone = phones[0].strip() if phones else ''
        
        # Extract names - STRICT patterns only
        name = ''
        strict_name_patterns = [
            r'(?:Professor|Dr\.)\s+([A-Z][a-z]+ [A-Z][a-z]+)(?:\s|$)',
            r'(?:Associate Professor|Assistant Professor)\s+([A-Z][a-z]+ [A-Z][a-z]+)(?:\s|$)'
        ]
        
        for pattern in strict_name_patterns:
            matches = re.findall(pattern, text)
            if matches:
                candidate = matches[0].strip()
                if self._is_confident_name(candidate):
                    name = candidate
                    break
        
        # Extract titles - STRICT patterns only
        title = ''
        strict_title_patterns = [
            r'\b(Professor)\b',
            r'\b(Associate Professor)\b',
            r'\b(Assistant Professor)\b',
            r'\b(Dr\.)\b'
        ]
        
        for pattern in strict_title_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                title = matches[0]
                break
        
        # Extract company - STRICT patterns only
        company = ''
        strict_company_patterns = [
            r'\b([A-Z][a-z]+ University)\b',
            r'\b([A-Z][a-z]+ College)\b',
            r'\b([A-Z][a-z]+ Institute)\b'
        ]
        
        for pattern in strict_company_patterns:
            matches = re.findall(pattern, text)
            if matches:
                company = matches[0]
                break
        
        return {
            'name': name,
            'title': title, 
            'company': company,
            'phone': phone
        }


    def _looks_like_name(self, text: str) -> bool:
        """Check if text looks like a person's name."""
        
        if len(text) < 2 or len(text) > 50:
            return False
        
        # Skip common non-name words
        skip_words = {
            'email', 'phone', 'contact', 'website', 'address', 'department',
            'university', 'college', 'school', 'company', 'organization'
        }
        
        if text.lower() in skip_words:
            return False
        
        # Must contain only letters, spaces, dots, apostrophes
        if not re.match(r"^[A-Za-z\s\.']+$", text):
            return False
        
        # Should have at least one space (first + last name)
        words = text.split()
        if len(words) < 2 or len(words) > 4:
            return False
        
        # Each word should be capitalized
        for word in words:
            if word and not word[0].isupper():
                return False
        
        return True

    def _is_valid_email_format_enhanced(self, email: str) -> bool:
        """Enhanced email format validation."""
        if not email or len(email) < 5 or len(email) > 254:
            return False
        
        # Must contain exactly one @
        if email.count('@') != 1:
            return False
        
        try:
            local, domain = email.split('@')
        except ValueError:
            return False
        
        if not local or not domain or '.' not in domain:
            return False
        
        # Enhanced pattern validation
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        return bool(email_pattern.match(email))

    def _infer_company_from_domain(self, email_domain: str, url: str) -> str:
        """Infer company name from email domain or URL."""
        
        # Educational institutions
        if '.edu' in email_domain:
            parts = email_domain.replace('.edu', '').split('.')
            if parts:
                name = parts[0].replace('-', ' ').title()
                return f"{name} University"
        
        # Extract from domain
        clean_domain = email_domain.replace('www.', '').split('.')[0]
        return clean_domain.replace('-', ' ').title()

    def _remove_duplicates(self, emails: List[Dict]) -> List[Dict]:
        """Remove duplicate emails, keeping the one with most information."""
        
        seen = {}
        for email_data in emails:
            email = email_data['email'].lower()
            
            if email not in seen:
                seen[email] = email_data
            else:
                # Keep the one with more complete information
                current = seen[email]
                if self._count_filled_fields(email_data) > self._count_filled_fields(current):
                    seen[email] = email_data
        
        return list(seen.values())

    def _count_filled_fields(self, email_data: Dict) -> int:
        """Count how many fields have meaningful data."""
        count = 0
        for key in ['name', 'title', 'company', 'phone']:
            if email_data.get(key) and email_data[key].strip():
                count += 1
        return count

    def _calculate_validation_score(self, email: str) -> float:
        """Calculate a validation score for the email."""
        score = 0.5  # Base score
        
        # Domain reputation
        if not email:
            return score
            
        try:
            domain = email.split('@')[1].lower()
            if any(tld in domain for tld in ['.edu', '.gov', '.org']):
                score += 0.2
            
            # Email format
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                score += 0.1
            
            # Not a generic email
            generic_prefixes = ['info', 'contact', 'admin', 'support', 'noreply']
            if not any(prefix in email.lower() for prefix in generic_prefixes):
                score += 0.1
        except:
            pass
        
        return min(score, 1.0)

    
    async def _process_results(self, crawl_results: List[CrawlResult], start_url: str) -> List[Dict]:
        """Process crawl results and export them."""
        try:
            # Combine all results
            all_contacts = []
            
            for result in crawl_results:
                for contact in result.contacts:
                    contact['source_url'] = result.url
                    contact['crawl_timestamp'] = result.timestamp
                    all_contacts.append(contact)
            
            # Validate and deduplicate
            if self.config.validate_emails:
                all_contacts = self.validator.validate_contacts(all_contacts)
            
            all_contacts = self.validator.deduplicate_contacts(all_contacts)
            
            # Export results
            output_file = await self.exporter.export_results(all_contacts, start_url)
            
            # Log summary
            logging.info(f"Crawl completed for {start_url}")
            logging.info(f"Pages crawled: {len(self.visited_urls)}")
            logging.info(f"Contacts found: {len(all_contacts)}")
            logging.info(f"Failed URLs: {len(self.failed_urls)}")
            logging.info(f"Results exported to: {output_file}")
            
            if self.failed_urls:
                logging.warning("Failed URLs:")
                for url, error in self.failed_urls.items():
                    logging.warning(f"  {url}: {error}")
            
            return all_contacts
            
        except Exception as e:
            logging.error(f"Error processing results: {e}")
            raise

    def extract_staff_directory(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract structured academic staff information from directories."""
        
        # Look for staff/faculty listings
        staff_sections = soup.find_all(['div', 'table', 'ul', 'section'], 
                                    class_=re.compile(r'(staff|faculty|academic|directory|team|people)', re.I))
        
        # Also check for common ID patterns
        staff_sections.extend(soup.find_all(['div', 'section'], 
                                        id=re.compile(r'(staff|faculty|team|people)', re.I)))
        
        structured_data = []
        
        for section in staff_sections:
            # Look for structured entries
            entries = section.find_all(['tr', 'li', 'div', 'article'])
            
            for entry in entries:
                text = entry.get_text(separator=' ', strip=True)
                
                # Find email addresses in this entry
                email_matches = re.findall(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text)
                
                for email in email_matches:
                    # Extract name and title from surrounding context
                    info = self.extract_person_info(entry, email)
                    if info:
                        structured_data.append({
                            'email': email,
                            'name': info.get('name', ''),
                            'title': info.get('title', ''),
                            'context': text[:200]  # First 200 chars for context
                        })
        
        return {'staff_data': structured_data, 'url': url}

    def extract_person_info(self, entry_element, email: str) -> Dict:
        """Extract person info from HTML element containing email."""
        
        # Try to find name in various elements
        name_elements = entry_element.find_all(['h1', 'h2', 'h3', 'h4', 'strong', 'b', 'span'])
        
        for element in name_elements:
            text = element.get_text(strip=True)
            
            # Look for names (2-4 words, capitalized)
            name_pattern = r'^([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+){1,2})$'
            if re.match(name_pattern, text):
                # Check if this name is near the email
                full_text = entry_element.get_text()
                if email.split('@')[0].lower() in text.lower().replace(' ', '').replace('.', ''):
                    return {'name': text, 'title': self.find_title_near_name(entry_element, text)}
        
        # Fallback: extract from full text
        full_text = entry_element.get_text()
        return self.extract_academic_info(full_text, email)

    def find_title_near_name(self, element, name: str) -> str:
        """Find academic title near a person's name."""
        
        titles = [
            'Professor', 'Prof', 'Associate Professor', 'Assistant Professor',
            'Dr', 'PhD', 'Director', 'Dean', 'Chair', 'Head',
            'Senior Lecturer', 'Lecturer', 'Research Fellow', 'Researcher'
        ]
        
        text = element.get_text()
        name_pos = text.find(name)
        
        if name_pos == -1:
            return ''
        
        # Look before and after the name (within 50 characters)
        context = text[max(0, name_pos-50):name_pos+len(name)+50]
        
        for title in titles:
            if re.search(rf'\b{re.escape(title)}\b', context, re.IGNORECASE):
                return title
        
        return ''
    
    def infer_name_from_email(self, email: str) -> str:
        """Better name inference from email addresses."""
        
        username = email.split('@')[0]
        
        # Common email patterns
        patterns = [
            # firstname.lastname
            r'^([a-z]+)\.([a-z]+)$',
            # firstname_lastname
            r'^([a-z]+)_([a-z]+)$',  
            # firstinitiallastname (jsmith)
            r'^([a-z])([a-z]{3,})$',
            # firstnamelastname (johnsmith - detect by common first names or length)
            r'^([a-z]{3,8})([a-z]{3,})$'
        ]
        
        for pattern in patterns:
            match = re.match(pattern, username.lower())
            if match:
                first = match.group(1).capitalize()
                last = match.group(2).capitalize()
                
                # Special handling for single letter first names
                if len(first) == 1:
                    return f"{first}. {last}"
                
                return f"{first} {last}"
        
        # If no pattern matches, capitalize the username
        return ' '.join(word.capitalize() for word in re.split(r'[._-]', username))

    def extract_institution_info(self, url: str, email_domain: str) -> str:
        """Extract proper institution name from URL and email domain."""
        
        # Common patterns for educational institutions
        if '.edu' in email_domain:
            # Extract university name from domain
            domain_parts = email_domain.replace('.edu', '').split('.')
            if len(domain_parts) >= 1:
                institution = domain_parts[0].replace('-', ' ').title()
                if 'university' not in institution.lower():
                    institution += ' University'
                return institution
        
        # Extract from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if 'university' in domain or 'college' in domain or '.edu' in domain:
            return domain.replace('www.', '').replace('.com', '').replace('.edu', '').replace('-', ' ').title()
        
        return 'Unknown'

    def enhance_extracted_data(self, results: List[Dict], url: str) -> List[Dict]:
        """Post-process results to improve accuracy."""
        
        enhanced = []
        
        for result in results:
            # Improve name if it's just the email prefix
            current_name = result.get('name', '')
            email = result.get('email', '')
            
            if not current_name or current_name.lower() == email.split('@')[0].lower():
                result['name'] = self.infer_name_from_email(email)
            
            # Improve company/institution
            if result.get('company') == 'Edu' or not result.get('company'):
                result['company'] = self.extract_institution_info(url, email.split('@')[1])
            
            # Clean up titles
            title = result.get('title', '')
            if title:
                # Standardize common titles
                title_mapping = {
                    'prof': 'Professor',
                    'assoc prof': 'Associate Professor',
                    'asst prof': 'Assistant Professor',
                    'dr': 'Dr.'
                }
                
                for abbrev, full in title_mapping.items():
                    if abbrev in title.lower():
                        result['title'] = full
                        break
            
            # Increase confidence if we have good name and title
            if result.get('name') and result.get('title'):
                result['confidence'] = min(result.get('confidence', 0.5) + 0.2, 1.0)
            
            enhanced.append(result)
        
        return enhanced