# Email Extractor - Advanced Web Crawler \& Contact Intelligence

A powerful Python tool for extracting emails, contact information, and social profiles from websites using advanced crawling techniques, JavaScript rendering, and AI-powered validation.

## ✨ Features

- **Multi-Method Email Detection**: Standard patterns, mailto links, obfuscated text, JavaScript-generated content
- **JavaScript Support**: Full SPA and React website compatibility with Playwright
- **Contact Intelligence**: Names, titles, companies, phone numbers, social profiles
- **Advanced Validation**: Real-time email verification and data quality scoring
- **OCR Extraction**: Extract emails from images and documents
- **Multi-Language Support**: Works with international websites (Turkish, Spanish, etc.)
- **Multiple Output Formats**: CSV, JSON, Excel with detailed analytics
- **Batch Processing**: Handle multiple domains simultaneously


## 🚀 Installation

```bash
python install.py  # Auto-installs all dependencies
```


## 🔧 OCR Setup (Optional)

For extracting emails from images, install Tesseract OCR:

### Windows
Download from: https://github.com/UB-Mannheim/tesseract/wiki
Or use chocolatey:
```bash
choco install tesseract
```

Or use conda:
```bash
conda install -c conda-forge tesseract
```

### Ubuntu/Debian
```bash
sudo apt install tesseract-ocr
```

### macOS
```bash
brew install tesseract
```

### Verify Installation
```bash
tesseract --version
```

**Note**: Add Tesseract to your system PATH if needed (Windows: `C:\Program Files\Tesseract-OCR`)


## 📋 Usage

### Basic Commands

```bash
# Single website extraction
python main.py --url https://example.com

# Batch processing from file
python main.py --urls-file websites.txt --output excel

# JavaScript-heavy sites (SPAs, React)
python main.py --url https://example.com --use-javascript

# High-quality extraction with validation
python main.py --url https://example.com --validate-emails --extract-social --output excel
```


### Complete Command Reference

```bash
python main.py --url <URL> [OPTIONS]

# Input Options:
  --url URL                   Single website to crawl
  --urls-file FILE            Text file with URLs (one per line)

# Crawling Control:
  --depth N                  1=single page only, 2=page+all its links, 3+=follow links from those pages (default: 5, max: 20)
  --max-pages N              Pages per domain (default: 1000)
  --delay SECONDS            Request delay (default: 1.0, max: 10.0)

# Output Options:
  --output FORMAT            csv|json|excel (default: csv)
  --output-dir DIR           Output folder (default: results)
  --output-file NAME         Custom filename

# Extraction Features:
  --validate-emails         Verify email addresses
  --use-javascript          JavaScript rendering for dynamic content
  --extract-social          Extract LinkedIn, Twitter, etc.
  --ocr-emails              Extract from images using OCR

# Filtering Options:
  --domains-only DOM1 DOM2   Only crawl specified domains
  --exclude-domains DOM1     Skip certain domains
  --exclude-extensions LIST  Skip file types (default: .pdf .doc .zip)

# Logging Options:
  -v, -vv, -vvv             Verbose output levels
  --quiet                   Show errors only
  --log-file FILE           Save logs to file
```


## 🏗️ Architecture

```
email_extractor/
├── main.py                      # Main CLI entry point and argument parsing
├── install.py                   # Automated dependency installation script
├── requirements.txt             # Python dependencies
│
├── crawler/
│   └── website_crawler.py      # Async web crawling engine with Playwright support
│
├── extractors/
│   ├── email_extractor.py      # Multi-method email extraction engine
│   └── contact_matcher.py      # AI-powered contact information association
│
├── utils/
│   ├── config.py               # Configuration management with Pydantic
│   ├── logger.py               # Advanced logging setup and management
│   ├── patterns.py             # 50+ regex patterns for email/contact detection
│   ├── text_processing.py      # NLP text cleaning and normalization
│   ├── validators.py           # Email validation and data quality scoring
│   ├── exporters.py            # Multi-format export (CSV, JSON, Excel)
│   └── progress_tracker.py     # Real-time crawling progress monitoring
│
├── logs/                       # Automatic log storage
└── results/                    # Default output directory
```


## 📊 Output Examples

### CSV Output

```csv
email,name,title,company,phone,source_url,extraction_method,confidence
john.doe@company.com,John Doe,Senior Developer,TechCorp,+1-555-0123,https://company.com/team,mailto_link,0.95
```


### JSON Output

```json
{
  "metadata": {
    "total_contacts": 47,
    "pages_crawled": 23,
    "extraction_methods": ["mailto_link", "standard_pattern", "javascript"]
  },
  "contacts": [
    {
      "email": "john.doe@company.com",
      "name": "John Doe",
      "title": "Senior Developer",
      "social_profiles": {
        "linkedin": "linkedin.com/in/johndoe"
      },
      "confidence": 0.95
    }
  ]
}
```


### Excel Output

Multi-sheet workbook with:

- **Contacts**: All extracted data
- **Summary**: Statistics by method/company
- **Analytics**: Detailed metrics


## 🔧 Configuration

Copy `.env.template` to `.env` and configure:

```bash
EMAIL_EXTRACTOR_MAX_DEPTH=5
EMAIL_EXTRACTOR_VALIDATE_EMAILS=true
EMAIL_EXTRACTOR_USE_JAVASCRIPT=false
EMAIL_EXTRACTOR_OUTPUT_FORMAT=csv
```


## 🚨 Legal \& Ethics

- Respects robots.txt automatically
- Built-in rate limiting prevents server overload
- Designed for legitimate business research
- Handle extracted data per GDPR/CCPA requirements

This tool is perfect for lead generation, academic research, business intelligence, and contact discovery from public web sources.