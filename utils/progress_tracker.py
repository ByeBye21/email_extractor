"""
Progress tracking utilities for monitoring crawl progress.
"""

import logging
import time
from typing import Dict, Optional
from tqdm import tqdm


class ProgressTracker:
    """Tracks and reports progress during website crawling."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.pages_crawled: int = 0
        self.emails_found: int = 0
        self.contacts_found: int = 0
        self.failed_pages: int = 0
        self.current_url: str = ""
        self.progress_bar: Optional[tqdm] = None
        self.last_update_time: float = time.time()
        
    def start_crawl(self, total_pages: Optional[int] = None):
        """Start tracking a new crawl."""
        self.start_time = time.time()
        self.pages_crawled = 0
        self.emails_found = 0
        self.contacts_found = 0
        self.failed_pages = 0
        
        if total_pages:
            self.progress_bar = tqdm(
                total=total_pages,
                desc="Crawling",
                unit="pages",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
            )
        
        logging.info("Started crawl progress tracking")
    
    def update_progress(self, url: str, emails_count: int = 0, contacts_count: int = 0, failed: bool = False):
        """Update progress with results from a single page."""
        self.current_url = url
        self.pages_crawled += 1
        self.emails_found += emails_count
        self.contacts_found += contacts_count
        
        if failed:
            self.failed_pages += 1
        
        # Update progress bar
        if self.progress_bar:
            self.progress_bar.update(1)
            self.progress_bar.set_postfix({
                'Emails': self.emails_found,
                'Contacts': self.contacts_found,
                'Failed': self.failed_pages
            })
        
        # Log periodic updates
        current_time = time.time()
        if current_time - self.last_update_time > 10:  # Every 10 seconds
            self._log_progress_update()
            self.last_update_time = current_time
    
    def _log_progress_update(self):
        """Log a progress update."""
        if self.start_time:
            elapsed = time.time() - self.start_time
            rate = self.pages_crawled / elapsed if elapsed > 0 else 0
            
            logging.info(
                f"Progress: {self.pages_crawled} pages crawled, "
                f"{self.emails_found} emails, {self.contacts_found} contacts found, "
                f"{self.failed_pages} failed, {rate:.2f} pages/sec"
            )
    
    def finish_crawl(self):
        """Finish tracking and log final statistics."""
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None
        
        if self.start_time:
            total_time = time.time() - self.start_time
            rate = self.pages_crawled / total_time if total_time > 0 else 0
            
            logging.info("Crawl completed!")
            logging.info(f"Total pages crawled: {self.pages_crawled}")
            logging.info(f"Total emails found: {self.emails_found}")
            logging.info(f"Total contacts found: {self.contacts_found}")
            logging.info(f"Failed pages: {self.failed_pages}")
            logging.info(f"Total time: {total_time:.2f} seconds")
            logging.info(f"Average rate: {rate:.2f} pages/second")
            
            if self.pages_crawled > 0:
                success_rate = ((self.pages_crawled - self.failed_pages) / self.pages_crawled) * 100
                logging.info(f"Success rate: {success_rate:.1f}%")
    
    def get_statistics(self) -> Dict:
        """Get current crawl statistics."""
        elapsed_time = time.time() - self.start_time if self.start_time else 0
        rate = self.pages_crawled / elapsed_time if elapsed_time > 0 else 0
        
        return {
            'pages_crawled': self.pages_crawled,
            'emails_found': self.emails_found,
            'contacts_found': self.contacts_found,
            'failed_pages': self.failed_pages,
            'elapsed_time': elapsed_time,
            'pages_per_second': rate,
            'success_rate': ((self.pages_crawled - self.failed_pages) / self.pages_crawled) * 100 if self.pages_crawled > 0 else 0,
            'current_url': self.current_url
        }
    
    def set_total_pages(self, total: int):
        """Set the total number of pages to crawl (updates progress bar)."""
        if self.progress_bar:
            self.progress_bar.total = total
            self.progress_bar.refresh()
    
    def log_milestone(self, message: str):
        """Log a milestone message."""
        logging.info(f"MILESTONE: {message}")
        if self.progress_bar:
            self.progress_bar.write(f"🎯 {message}")