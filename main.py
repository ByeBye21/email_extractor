#!/usr/bin/env python3
"""
Email Extractor - Web Crawler & Contact Extractor
Production-grade Python application for crawling websites and extracting contact information.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional

# Check for required dependencies
missing_deps = []
try:
    import httpx
except ImportError:
    missing_deps.append("httpx")

try:
    from bs4 import BeautifulSoup
except ImportError:
    missing_deps.append("beautifulsoup4")

try:
    import pandas as pd
except ImportError:
    missing_deps.append("pandas")

if missing_deps:
    print("❌ Missing required dependencies:")
    for dep in missing_deps:
        print(f"   - {dep}")
    print("\nInstall with: pip install " + " ".join(missing_deps))
    sys.exit(1)

try:
    from crawler.website_crawler import WebsiteCrawler
    from utils.config import Config
    from utils.logger import setup_logging
    from utils.validators import validate_url
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("\nTry:")
    print("1. Ensure all files are in the correct directories")
    print("2. Create __init__.py files in all directories")
    sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Web Crawler & Contact Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url https://example.com --depth 3
  python main.py --url https://company.com --depth 5 --output json --validate-emails
  python main.py --urls-file websites.txt --output-dir results/
        """
    )
    
    # URL input options
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument(
        "--url", "-u",
        type=str,
        help="Single URL to crawl"
    )
    url_group.add_argument(
        "--urls-file", "-f",
        type=str,
        help="File containing URLs to crawl (one per line)"
    )
    
    # Crawling options
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=3,
        help="Crawling depth (default: 3)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1000,
        help="Maximum pages to crawl per domain (default: 1000)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default="EmailExtractor/1.0 (+https://github.com/example/email-extractor)",
        help="Custom user agent string"
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        choices=["csv", "json", "excel"],
        default="csv",
        help="Output format (default: csv)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Output directory (default: results)"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Output filename (auto-generated if not specified)"
    )
    
    # Processing options
    parser.add_argument(
        "--validate-emails",
        action="store_true",
        help="Validate email addresses"
    )
    parser.add_argument(
        "--use-javascript",
        action="store_true",
        help="Enable JavaScript rendering for SPA sites"
    )
    parser.add_argument(
        "--extract-social",
        action="store_true",
        help="Extract social media profiles"
    )
    parser.add_argument(
        "--ocr-emails",
        action="store_true",
        help="Extract emails from images using OCR"
    )
    
    # Filtering options
    parser.add_argument(
        "--domains-only",
        nargs="+",
        help="Only crawl specified domains"
    )
    parser.add_argument(
        "--exclude-domains",
        nargs="+",
        help="Exclude specified domains"
    )
    parser.add_argument(
        "--exclude-extensions",
        nargs="+",
        default=[".pdf", ".doc", ".docx", ".zip", ".rar"],
        help="File extensions to exclude"
    )
    
    # Logging options
    parser.add_argument(
        "--verbose", "-v",
        action="count",
        default=0,
        help="Increase verbosity (use -v, -vv, or -vvv)"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress all output except errors"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path"
    )
    
    return parser.parse_args()


def load_urls_from_file(file_path: str) -> List[str]:
    """Load URLs from a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        # Validate URLs
        valid_urls = []
        for url in urls:
            if validate_url(url):
                valid_urls.append(url)
            else:
                logging.warning(f"Invalid URL skipped: {url}")
        
        return valid_urls
    
    except FileNotFoundError:
        logging.error(f"URLs file not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error reading URLs file: {e}")
        sys.exit(1)


async def crawl_single_url(url: str, config: Config) -> bool:
    """Crawl a single URL and return success status."""
    try:
        logging.info(f"Starting crawl for: {url}")
        
        crawler = WebsiteCrawler(config)
        results = await crawler.crawl_website(url)
        
        if results:
            logging.info(f"Crawl completed for {url}. Found {len(results)} contacts.")
            return True
        else:
            logging.warning(f"No contacts found for: {url}")
            return False
            
    except Exception as e:
        logging.error(f"Error crawling {url}: {e}")
        return False


async def crawl_multiple_urls(urls: List[str], config: Config) -> None:
    """Crawl multiple URLs concurrently."""
    logging.info(f"Starting crawl for {len(urls)} URLs")
    
    # Limit concurrent crawls to avoid overwhelming targets
    semaphore = asyncio.Semaphore(3)
    
    async def crawl_with_semaphore(url: str) -> bool:
        async with semaphore:
            return await crawl_single_url(url, config)
    
    # Run crawls concurrently
    tasks = [crawl_with_semaphore(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count successes
    successful = sum(1 for result in results if result is True)
    logging.info(f"Completed crawling. {successful}/{len(urls)} URLs successful.")


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Setup logging
    log_level = logging.WARNING
    if args.quiet:
        log_level = logging.ERROR
    elif args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
    
    setup_logging(log_level, args.log_file)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create configuration
    config = Config(
        max_depth=args.depth,
        max_pages=args.max_pages,
        delay=args.delay,
        user_agent=args.user_agent,
        output_format=args.output,
        output_dir=str(output_dir),
        output_file=args.output_file,
        validate_emails=args.validate_emails,
        use_javascript=args.use_javascript,
        extract_social=args.extract_social,
        ocr_emails=args.ocr_emails,
        allowed_domains=args.domains_only,
        excluded_domains=args.exclude_domains,
        excluded_extensions=args.exclude_extensions
    )
    
    try:
        # Get URLs to crawl
        if args.url:
            if not validate_url(args.url):
                logging.error(f"Invalid URL: {args.url}")
                sys.exit(1)
            urls = [args.url]
        else:
            urls = load_urls_from_file(args.urls_file)
            if not urls:
                logging.error("No valid URLs found in file")
                sys.exit(1)
        
        # Start crawling
        if len(urls) == 1:
            asyncio.run(crawl_single_url(urls[0], config))
        else:
            asyncio.run(crawl_multiple_urls(urls, config))
            
    except KeyboardInterrupt:
        logging.info("Crawling interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()