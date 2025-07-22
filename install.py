#!/usr/bin/env python3
"""
Installation and setup script for Email Extractor
- Checks and installs dependencies from requirements.txt
- Sets up configuration files
- Checks system requirements
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def print_banner():
    """Display installation banner."""
    print("Email Extractor - Installation Script")
    print("====================================")


def check_python_version():
    """Ensure Python version compatibility."""
    print("Checking Python version...")
    
    if sys.version_info < (3, 8):
        print("ERROR: Python 3.8+ is required")
        print(f"Current version: {sys.version}")
        return False
    
    print(f"OK: Python {sys.version.split()[0]} detected")
    return True


def is_package_installed(package_name):
    """Check if a package is already installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except:
        return False


def get_package_name(package_spec):
    """Extract package name from requirement specification."""
    package_name = package_spec.split('==')[0].split('>=')[0].split('<=')[0].split('>')[0].split('<')[0].split('[')[0]
    return package_name.strip()


def install_requirements():
    """Install packages from requirements.txt if not already installed."""
    print("\nChecking dependencies from requirements.txt...")
    
    if not Path("requirements.txt").exists():
        print("ERROR: requirements.txt not found")
        return False
    
    try:
        with open("requirements.txt", "r") as f:
            requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        print(f"Found {len(requirements)} packages to check")
        
        # Check which packages need installation
        missing_packages = []
        installed_count = 0
        
        for package in requirements:
            if package:
                package_name = get_package_name(package)
                
                if is_package_installed(package_name):
                    print(f"SKIP: {package_name} already installed")
                    installed_count += 1
                else:
                    missing_packages.append(package)
        
        if not missing_packages:
            print("All packages already installed!")
            return True
        
        print(f"\nInstalling {len(missing_packages)} missing packages...")
        print(f"Skipped {installed_count} already installed packages")
        
        # Install all missing packages
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + missing_packages,
            check=False
        )
        
        if result.returncode == 0:
            print("All packages installed successfully")
            return True
        else:
            print("Some packages failed to install")
            return False
        
    except Exception as e:
        print(f"ERROR: Failed to install dependencies: {e}")
        return False


def download_spacy_model():
    """Download spaCy English model after spaCy installation."""
    print("\nDownloading spaCy English model...")
    
    if not is_package_installed("spacy"):
        print("SKIP: spaCy not installed")
        return True
    
    try:
        # Check if model already exists
        result = subprocess.run(
            [sys.executable, "-c", "import spacy; spacy.load('en_core_web_sm'); print('Model exists')"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("OK: en_core_web_sm model already installed")
            return True
        
        # Download the model
        print("Downloading en_core_web_sm model...")
        result = subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
            check=False
        )
        
        if result.returncode == 0:
            print("spaCy model downloaded successfully")
            return True
        else:
            print("WARNING: Failed to download spaCy model")
            return False
            
    except Exception as e:
        print(f"WARNING: Error downloading spaCy model: {e}")
        return False


def setup_playwright():
    """Install Playwright browsers."""
    print("\nSetting up Playwright browsers...")
    
    if not is_package_installed("playwright"):
        print("SKIP: Playwright not installed")
        return True
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print("Playwright browsers installed successfully")
            return True
        else:
            print(f"WARNING: Playwright setup failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"WARNING: Error setting up Playwright: {e}")
        return False


def check_tesseract():
    """Check if Tesseract OCR is installed."""
    print("\nChecking Tesseract OCR...")
    
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"OK: {version_line}")
            return True
        else:
            print("WARNING: Tesseract OCR not found in PATH")
            return False
            
    except FileNotFoundError:
        print("WARNING: Tesseract OCR not installed")
        print("Install from: https://github.com/UB-Mannheim/tesseract/wiki")
        return False
    except Exception as e:
        print(f"WARNING: Error checking Tesseract: {e}")
        return False


def create_config_files():
    """Create configuration files and directories."""
    print("\nCreating configuration files...")
    
    # Create directories
    directories = ["results", "logs", "temp"]
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"Created directory: {directory}")
    
    # Create .env template
    env_template = """# Email Extractor Configuration
# Copy this to .env and customize

# Basic settings
EMAIL_EXTRACTOR_MAX_DEPTH=5
EMAIL_EXTRACTOR_MAX_PAGES=1000
EMAIL_EXTRACTOR_DELAY=1.0
EMAIL_EXTRACTOR_OUTPUT_FORMAT=csv
EMAIL_EXTRACTOR_VALIDATE_EMAILS=false
EMAIL_EXTRACTOR_USE_JAVASCRIPT=false
EMAIL_EXTRACTOR_OCR_EMAILS=false

# CRM Integration (optional)
# SALESFORCE_USERNAME=your_username
# SALESFORCE_PASSWORD=your_password
# SALESFORCE_TOKEN=your_token
# HUBSPOT_API_KEY=your_api_key

# Advanced settings
# EMAIL_EXTRACTOR_USER_AGENT="EmailExtractor/1.0"
# EMAIL_EXTRACTOR_REQUESTS_PER_SECOND=1.0
# EMAIL_EXTRACTOR_CONCURRENT_REQUESTS=3
"""
    
    if not Path(".env.example").exists():
        with open(".env.example", "w") as f:
            f.write(env_template)
        print("Created .env.example template")
    
    # Create gitignore
    gitignore_content = """.env
results/
logs/
temp/
__pycache__/
*.pyc
*.log
.vscode/
.idea/
"""
    
    if not Path(".gitignore").exists():
        with open(".gitignore", "w") as f:
            f.write(gitignore_content)
        print("Created .gitignore")


def main():
    """Main installation process."""
    print_banner()
    
    if not check_python_version():
        sys.exit(1)
    
    if not install_requirements():
        print("\nERROR: Dependency installation failed")
        sys.exit(1)
    
    download_spacy_model()
    setup_playwright()
    check_tesseract()
    create_config_files()
    
    print("\n" + "="*50)
    print("Installation completed successfully!")
    print("\nNext steps:")
    print("1. Copy .env.example to .env and customize")
    print("2. Run: python main.py --help")
    print("3. Test: python main.py --url https://example.com")
    print("="*50)


if __name__ == "__main__":
    main()