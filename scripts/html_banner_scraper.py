#!/usr/bin/env python3
"""
HTML5 Banner Scraper

This script uses Selenium to fetch HTML5 banner designs from the provided URLs.
It extracts the HTML content, saves it locally, and can optionally take screenshots
of the rendered banners.

Features:
- Fetches HTML content from each banner URL
- Saves HTML files locally with organized directory structure
- Takes screenshots of rendered banners
- Handles JavaScript-heavy content with proper wait times
- Includes error handling and retry logic
- Supports batch processing with progress tracking

Usage:
    python html_banner_scraper.py [options]

Requirements:
    - selenium
    - beautifulsoup4
    - requests
    - Chrome/Chromium browser
    - ChromeDriver (automatically managed by selenium 4+)
"""

import json
import os
import sys
import time
import logging
import argparse
import hashlib
import mimetypes
import re
import io
import copy
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set, Any
from urllib.parse import urlparse, unquote, urljoin, urlunparse, quote
import requests
from bs4 import BeautifulSoup, Tag
import asyncio
import aiohttp
import aiofiles
from concurrent.futures import ThreadPoolExecutor
import imghdr
import struct

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


class HTMLBannerScraper:
    """
    Scraper for HTML5 banner designs using Selenium WebDriver.
    """
    
    def __init__(self, output_dir: str = "scraped_banners", headless: bool = True, 
                 timeout: int = 15, screenshot: bool = False, control_animations: bool = True,
                 global_assets: bool = False, parallel_downloads: bool = True, force: bool = False):
        """
        Initialize the scraper.
        
        Args:
            output_dir: Directory to save scraped content
            headless: Run browser in headless mode
            timeout: Timeout for page loads in seconds
            screenshot: Whether to take screenshots
            control_animations: Whether to let animations complete once then prevent looping
            global_assets: If True, download assets to global directory for reuse across projects
            parallel_downloads: If True, download assets in parallel for better performance
            force: If True, force re-scraping of already scraped projects instead of skipping them
        """
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.timeout = timeout
        self.screenshot = screenshot
        self.control_animations = control_animations
        self.global_assets = global_assets
        self.parallel_downloads = parallel_downloads
        self.force = force
        self.driver: Optional[webdriver.Chrome] = None
        
        # Initialize download failure tracking
        self._download_failures = 0
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        # Setup logging
        self._setup_logging()
        # Create global assets directory if using global assets
        if self.global_assets:
            self.global_assets_dir = self.output_dir / 'global_assets'
            self.global_assets_dir.mkdir(exist_ok=True)
            self.logger = logging.getLogger(__name__)  # Temporary logger for early logging
            self.logger.info(f"🌍 Global assets mode enabled: {self.global_assets_dir}")
        
        
        
        # Stats tracking
        self.stats = {
            'total_urls': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0
        }
        
        # Asset cache to track downloaded assets
        # Key: original URL, Value: local path
        self.asset_cache = {}
        
        # Download failure tracking for strict success validation
        self._download_failures = 0
        
        # Load existing global asset cache if using global assets
        if self.global_assets:
            self._load_global_asset_cache()

    def _normalize_url(self, url: str, base_url: Optional[str] = None) -> str:
        """
        Normalize a URL by properly encoding special characters and resolving relative URLs.
        This ensures consistent URL handling across all operations including cache lookup.
        
        Args:
            url: URL to normalize (can be relative or absolute)
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Normalized URL with proper encoding
        """
        if not url or url.startswith(('data:', 'javascript:', '#')):
            return url
            
        try:
            # Handle absolute vs relative URLs
            if url.startswith(('http://', 'https://')):
                # Already absolute URL, just normalize encoding
                full_url = url
            else:
                # Relative URL, resolve against base URL
                if base_url:
                    full_url = urljoin(base_url, url)
                else:
                    # Can't resolve relative URL without base
                    return url
            
            # Parse the URL to handle encoding properly
            parsed = urlparse(full_url)
            
            # Decode and re-encode path components to avoid double encoding
            # Split path, decode each part (potentially multiple times), then properly encode
            path_parts = parsed.path.split('/')
            encoded_parts = []
            for part in path_parts:
                if part:  # Don't encode empty parts (would become %2F)
                    # Repeatedly decode to handle multiple levels of encoding like %2520 -> %20 -> space
                    decoded_part = part
                    previous_decoded = None
                    
                    while decoded_part != previous_decoded:
                        previous_decoded = decoded_part
                        try:
                            decoded_part = unquote(decoded_part)
                        except:
                            break  # Stop if decoding fails
                    
                    # Then encode properly with safe characters for URLs
                    encoded_part = quote(decoded_part, safe='-._~')
                    encoded_parts.append(encoded_part)
                else:
                    encoded_parts.append(part)
            
            encoded_path = '/'.join(encoded_parts)
            
            # Handle query parameters with special care for Google Fonts
            if parsed.query:
                # Special handling for Google Fonts URLs
                if 'fonts.googleapis.com' in parsed.netloc.lower():
                    # For Google Fonts, we need to preserve the specific encoding they expect
                    # Decode to get clean parameters, then use their preferred format
                    decoded_query = parsed.query
                    # Repeatedly decode to remove multiple levels of encoding
                    previous_decoded = None
                    while decoded_query != previous_decoded:
                        previous_decoded = decoded_query
                        try:
                            decoded_query = unquote(decoded_query)
                        except:
                            break
                    
                    # For Google Fonts, preserve the decoded format completely
                    # Google Fonts expects: family=Roboto+Slab:700,regular,300
                    # Google Fonts expects: family=Oswald:700|Raleway:600,700,500
                    # Don't re-encode + : , | characters - they need to stay as-is
                    encoded_query = decoded_query
                else:
                    # Standard URL encoding for other domains
                    decoded_query = unquote(parsed.query)
                    encoded_query = quote(decoded_query, safe='=&')
            else:
                encoded_query = ''
            
            # Reconstruct the URL with proper encoding
            normalized_url = urlunparse((
                parsed.scheme,
                parsed.netloc,  # Don't encode netloc (domain names)
                encoded_path,
                parsed.params,  # Params are usually already encoded
                encoded_query,
                parsed.fragment  # Fragments are usually already encoded
            ))
            
            return normalized_url
            
        except Exception as e:
            self.logger.warning(f"Failed to normalize URL '{url}': {e}")
            # Return original URL if normalization fails
            return url

    def _get_expected_content_type(self, url: str) -> str:
        """
        Determine the expected content type based on file extension in URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            Expected content type category ('image', 'css', 'javascript', 'font', 'other')
        """
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Special case: Google Fonts CSS URLs (both css path and css query)
        if 'fonts.googleapis.com' in parsed.netloc.lower() and (
            'css' in parsed.path.lower() or 'css' in parsed.query.lower() or 
            parsed.path.lower().startswith('/css')
        ):
            return 'css'
        
        # Image extensions
        if any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico']):
            return 'image'
        
        # CSS files
        if path.endswith('.css'):
            return 'css'
        
        # JavaScript files
        if any(path.endswith(ext) for ext in ['.js', '.mjs']):
            return 'javascript'
        
        # Font files
        if any(path.endswith(ext) for ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot']):
            return 'font'
        
        # Other known types
        if any(path.endswith(ext) for ext in ['.xml', '.json', '.txt']):
            return 'text'
        
        return 'other'

    def _validate_content_type(self, content: bytes, expected_type: str, content_type_header: str = "") -> bool:
        """
        Validate that downloaded content matches expected type using multiple methods.
        
        Args:
            content: Downloaded content bytes
            expected_type: Expected content type ('image', 'css', 'javascript', 'font', 'other')
            content_type_header: Content-Type header from response
            
        Returns:
            True if content matches expected type, False otherwise
        """
        if not content:
            return False
        
        try:
            # Method 1: Check magic bytes/file signatures
            if self._validate_by_magic_bytes(content, expected_type):
                return True
            
            # Method 2: Check Content-Type header
            if self._validate_by_content_type_header(content_type_header, expected_type):
                return True
            
            # Method 3: Content analysis for text-based files
            if expected_type in ['css', 'javascript', 'text'] and self._validate_text_content(content, expected_type):
                return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Content validation error: {e}")
            # If validation fails due to error, be permissive but log it
            return True

    def _validate_by_magic_bytes(self, content: bytes, expected_type: str) -> bool:
        """
        Validate content using magic bytes/file signatures.
        
        Args:
            content: File content bytes
            expected_type: Expected content type
            
        Returns:
            True if magic bytes match expected type
        """
        if len(content) < 4:
            return False
        
        # Image magic bytes
        if expected_type == 'image':
            # JPEG
            if content[:2] == b'\xff\xd8':
                return True
            # PNG
            if content[:8] == b'\x89PNG\r\n\x1a\n':
                return True
            # GIF
            if content[:6] in [b'GIF87a', b'GIF89a']:
                return True
            # WebP
            if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
                return True
            # BMP
            if content[:2] == b'BM':
                return True
            # ICO
            if content[:4] == b'\x00\x00\x01\x00':
                return True
            # SVG (XML-based, check for SVG tag)
            if b'<svg' in content[:200].lower():
                return True
        
        # Font magic bytes
        elif expected_type == 'font':
            # WOFF
            if content[:4] == b'wOFF':
                return True
            # WOFF2
            if content[:4] == b'wOF2':
                return True
            # TTF/OTF
            if content[:4] in [b'\x00\x01\x00\x00', b'OTTO', b'true', b'typ1']:
                return True
            # EOT
            if len(content) > 34 and struct.unpack('<L', content[34:38])[0] == 0x504C:
                return True
        
        return False

    def _validate_by_content_type_header(self, content_type_header: str, expected_type: str) -> bool:
        """
        Validate content using HTTP Content-Type header.
        
        Args:
            content_type_header: Content-Type header value
            expected_type: Expected content type
            
        Returns:
            True if header matches expected type
        """
        if not content_type_header:
            return False
        
        content_type_lower = content_type_header.lower()
        
        if expected_type == 'image':
            return any(img_type in content_type_lower for img_type in [
                'image/jpeg', 'image/png', 'image/gif', 'image/svg', 'image/webp', 
                'image/bmp', 'image/x-icon', 'image/vnd.microsoft.icon'
            ])
        
        elif expected_type == 'css':
            return 'text/css' in content_type_lower
        
        elif expected_type == 'javascript':
            return any(js_type in content_type_lower for js_type in [
                'application/javascript', 'application/x-javascript', 'text/javascript'
            ])
        
        elif expected_type == 'font':
            return any(font_type in content_type_lower for font_type in [
                'font/', 'application/font', 'application/x-font', 'application/vnd.ms-fontobject'
            ])
        
        elif expected_type == 'text':
            return any(text_type in content_type_lower for text_type in [
                'text/', 'application/json', 'application/xml'
            ])
        
        return False

    def _validate_text_content(self, content: bytes, expected_type: str) -> bool:
        """
        Validate text-based content by analyzing its structure.
        
        Args:
            content: File content bytes
            expected_type: Expected content type
            
        Returns:
            True if content structure matches expected type
        """
        try:
            # Try to decode as text
            text_content = content.decode('utf-8', errors='ignore')[:1000]  # Check first 1000 chars
            text_lower = text_content.lower().strip()
            
            if expected_type == 'css':
                # CSS should contain CSS-like syntax
                css_indicators = ['{', '}', ':', ';', '@media', '@import', '@font-face', 'px', 'em', '%']
                return any(indicator in text_lower for indicator in css_indicators)
            
            elif expected_type == 'javascript':
                # JavaScript should contain JS-like syntax
                js_indicators = ['function', 'var ', 'let ', 'const ', '=>', 'window.', 'document.', 'console.']
                return any(indicator in text_lower for indicator in js_indicators)
            
            elif expected_type == 'text':
                # For text files, just check if it's mostly readable
                try:
                    content.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
            
        except Exception:
            pass
        
        return False

    async def _create_async_session(self, base_url: str) -> aiohttp.ClientSession:
        """
        Create an async HTTP session with proper headers and cookies.
        
        Args:
            base_url: Base URL for setting referer
            
        Returns:
            Configured aiohttp ClientSession
        """
        # Get cookies from Selenium driver if available
        cookies = {}
        if self.driver:
            selenium_cookies = self.driver.get_cookies()
            for cookie in selenium_cookies:
                cookies[cookie['name']] = cookie['value']
        
        # Set browser-like headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': base_url
        }
        
        # Create session with timeout
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)  # Limit concurrent connections
        
        return aiohttp.ClientSession(
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            connector=connector
        )
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_file = self.output_dir / 'scraper.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
            handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _setup_driver(self) -> webdriver.Chrome:
        """
        Setup Chrome WebDriver with optimal settings.
        
        Returns:
            Configured Chrome WebDriver instance
        """
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Performance and stability options
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')  # Skip image loading for faster performance
        chrome_options.add_argument('--disable-javascript-harmony-shipping')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        
        # User agent to avoid detection
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        # Window size for consistent screenshots
        chrome_options.add_argument('--window-size=1920,1080')
        
        try:
            # Selenium 4+ automatically manages ChromeDriver
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(self.timeout)
            return driver
        except Exception as e:
            self.logger.error(f"Failed to setup Chrome driver: {e}")
            raise
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for safe filesystem storage.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove/replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Decode URL-encoded characters
        filename = unquote(filename)
        
        # Remove extra spaces and limit length
        filename = filename.strip()[:200]
        
        return filename
    
    def _extract_banner_info(self, url: str) -> Tuple[str, str, str]:
        """
        Extract banner information from URL.
        
        Args:
            url: Banner URL
            
        Returns:
            Tuple of (banner_id, size, sanitized_filename)
        """
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.split('/')
        
        # Extract banner ID and size from URL structure
        banner_id = "unknown"
        size = "unknown"
        
        for i, part in enumerate(path_parts):
            if part.upper() in ['TT023', 'TT022', 'SE026', 'PS042', 'MU019', 'BU025', 'ER01'] or \
               any(prefix in part.upper() for prefix in ['TT', 'SE', 'PS', 'MU', 'BU', 'ER', 'HF']):
                banner_id = part.lower()
                # Look for size in next parts
                for j in range(i+1, len(path_parts)):
                    if 'x' in path_parts[j] and path_parts[j].replace('x', '').replace('0', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '') == '':
                        size = path_parts[j]
                        break
                break
        
        filename = f"{banner_id}_{size}"
        return banner_id, size, self._sanitize_filename(filename)
    
    def _disable_animations(self) -> None:
        """
        Allow GWD animations to complete their first cycle, then prevent looping.
        Enhanced with better detection and diagnostics.
        """
        if not self.driver:
            return
            
        try:
            # First, let's diagnose what we're actually dealing with
            diagnostic_script = """
            console.log('=== ANIMATION DIAGNOSTIC START ===');
            
            // Check what's available
            var hasGWD = !!(window.gwd && window.gwd.actions && window.gwd.actions.timeline);
            var hasStudio = !!(window.studio);
            var hasEnabler = !!(window.Enabler);
            
            console.log('GWD available:', hasGWD);
            console.log('Studio available:', hasStudio);
            console.log('Enabler available:', hasEnabler);
            
            // Check animation elements
            var animatedElements = document.querySelectorAll('[class*="gwd-gen-"]');
            console.log('Found', animatedElements.length, 'GWD animated elements');
            
            // Check event animation
            var eventElement = document.querySelector('.gwd-animation-event, [class*="event-"]');
            if (eventElement) {
                var style = window.getComputedStyle(eventElement);
                console.log('Event animation duration:', style.animationDuration);
                console.log('Event animation name:', style.animationName);
            }
            
            // Check page state
            var page = document.querySelector('#page1, gwd-page');
            if (page) {
                console.log('Page classes:', page.className);
                console.log('Page has start class:', page.classList.contains('start'));
                console.log('Page has gwd-play-animation class:', page.classList.contains('gwd-play-animation'));
            }
            
            console.log('=== ANIMATION DIAGNOSTIC END ===');
            
            return {
                hasGWD: hasGWD,
                hasStudio: hasStudio,
                hasEnabler: hasEnabler,
                animatedElementsCount: animatedElements.length,
                hasEventElement: !!eventElement,
                pageState: page ? page.className : null
            };
            """
            
            # Run diagnostics first
            diagnostic_result = self.driver.execute_script(diagnostic_script)
            self.logger.info(f"🔍 Animation diagnostic: {diagnostic_result}")
            
            # Wait a bit for page to fully load
            time.sleep(2)
            
            # Now run the actual animation control
            animation_control_script = """
            console.log('Setting up animation control...');
            
            var animationDuration = 6000; // Default 6 seconds - longer to be safe
            var controlsSet = false;
            
            // Check if GWD is available
            if (window.gwd && window.gwd.actions && window.gwd.actions.timeline) {
                console.log('GWD timeline found, setting up controls...');
                
                // Get animation duration from event element
                var eventElement = document.querySelector('.gwd-animation-event, [class*="event-"]');
                if (eventElement) {
                    var style = window.getComputedStyle(eventElement);
                    var duration = style.animationDuration;
                    if (duration && duration !== '0s') {
                        var match = duration.match(/([0-9.]+)s/);
                        if (match) {
                            animationDuration = (parseFloat(match[1]) + 1) * 1000; // Add 1 second buffer
                            console.log('Duration from event element:', animationDuration + 'ms');
                        }
                    }
                }
                
                // Set up timeline pause after completion
                setTimeout(function() {
                    try {
                        if (window.gwd.actions.timeline.pause) {
                            window.gwd.actions.timeline.pause();
                            console.log('Timeline paused');
                        }
                        
                        // Override restart methods
                        window.gwd.actions.timeline.gotoAndPlay = function() { 
                            console.log('gotoAndPlay blocked'); 
                            return false; 
                        };
                        window.gwd.actions.timeline.play = function() { 
                            console.log('play blocked'); 
                            return false; 
                        };
                        
                        console.log('Timeline controls overridden');
                    } catch (e) {
                        console.error('Error in timeline control:', e);
                    }
                }, animationDuration);
                
                controlsSet = true;
            } else {
                console.log('No GWD timeline found, using fallback');
                animationDuration = 5000; // 5 second fallback
            }
            
            // Also handle any infinite animations immediately
            try {
                var infiniteElements = document.querySelectorAll('[style*="infinite"], [class*="infinite"]');
                infiniteElements.forEach(function(el) {
                    el.style.animationIterationCount = '1';
                    el.style.animationFillMode = 'forwards';
                    console.log('Stopped infinite animation on:', el.tagName, el.id);
                });
            } catch (e) {
                console.log('No infinite animations to handle');
            }
            
            return {
                duration: animationDuration,
                controlsSet: controlsSet,
                timestamp: Date.now()
            };
            """
            
            # Execute animation control
            result = self.driver.execute_script(animation_control_script)
            
            if result:
                duration = result.get('duration', 6000)
                controls_set = result.get('controlsSet', False)
                
                if controls_set:
                    self.logger.info("✅ GWD animation controls configured")
                else:
                    self.logger.info("⚠️ Using fallback animation handling")
                
                self.logger.info(f"⏱️ Waiting {duration/1000:.1f}s for animations to complete...")
                
                # Wait for animations with progress updates
                wait_time = duration / 1000
                progress_interval = max(1, wait_time / 4)  # Update 4 times during wait
                
                for i in range(int(wait_time / progress_interval)):
                    time.sleep(progress_interval)
                    remaining = wait_time - (i + 1) * progress_interval
                    if remaining > 0:
                        self.logger.info(f"⏱️ {remaining:.1f}s remaining...")
                
                # Final wait for any remaining time
                remaining_time = wait_time - (int(wait_time / progress_interval) * progress_interval)
                if remaining_time > 0:
                    time.sleep(remaining_time)
                
                self.logger.info("✅ Animation wait completed")
                
                # Extra buffer to ensure everything is settled
                time.sleep(1)
                
        except Exception as e:
            self.logger.warning(f"Failed to control animations: {e}")
            # Conservative fallback
            self.logger.info("⏱️ Using conservative fallback: waiting 8s...")
            time.sleep(8)

    def _take_banner_screenshot(self, screenshot_file: Path, size: str) -> None:
        """
        Take a screenshot of just the banner content, cropping out empty areas.
        
        Args:
            screenshot_file: Path to save the screenshot
            size: Banner size (e.g., "160x600")
        """
        if not self.driver:
            raise Exception("Driver not initialized")
            
        try:
            # Allow animations to complete first for proper layout (if enabled)
            if self.control_animations:
                self._disable_animations()
            
            # Parse expected dimensions
            expected_width, expected_height = None, None
            if 'x' in size:
                try:
                    expected_width, expected_height = map(int, size.split('x'))
                except ValueError:
                    pass
            
            # Try to find the main banner container
            banner_element = None
            
            # Common selectors for banner containers
            selectors = [
                'div[id*="banner"]',
                'div[class*="banner"]',
                'div[id*="gwd"]',  # Google Web Designer
                'div[class*="gwd"]',
                'div[id*="ad"]',
                'div[class*="ad"]',
                '.ad-container',
                '#ad-container',
                'body > div:first-child',  # Often the main container
                'canvas',  # Some banners use canvas
                'svg'  # SVG banners
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        # Check if element has reasonable dimensions
                        size_info = element.size
                        location = element.location
                        
                        if (size_info['width'] > 50 and size_info['height'] > 50 and
                            location['x'] >= 0 and location['y'] >= 0):
                            
                            # If we have expected dimensions, prefer elements that match
                            if expected_width and expected_height:
                                width_diff = abs(size_info['width'] - expected_width)
                                height_diff = abs(size_info['height'] - expected_height)
                                # Allow some tolerance (up to 10% difference)
                                if (width_diff <= expected_width * 0.1 and 
                                    height_diff <= expected_height * 0.1):
                                    banner_element = element
                                    break
                            else:
                                banner_element = element
                                break
                    
                    if banner_element:
                        break
                except:
                    continue
            
            if banner_element:
                # Take screenshot of specific element
                banner_element.screenshot(str(screenshot_file))
                self.logger.info(f"Captured element screenshot: {banner_element.tag_name} with size {banner_element.size}")
            else:
                # Fallback: try to crop the full screenshot intelligently
                self._take_cropped_screenshot(screenshot_file, expected_width, expected_height)
                
        except Exception as e:
            self.logger.warning(f"Failed to take targeted screenshot: {e}")
            # Final fallback: regular screenshot
            if self.driver:
                self.driver.save_screenshot(str(screenshot_file))
    
    def _take_cropped_screenshot(self, screenshot_file: Path, expected_width: Optional[int], expected_height: Optional[int]) -> None:
        """
        Take a full screenshot and crop it to remove empty areas.
        
        Args:
            screenshot_file: Path to save the screenshot
            expected_width: Expected banner width
            expected_height: Expected banner height
        """
        if not self.driver:
            raise Exception("Driver not initialized")
            
        try:
            from PIL import Image
            import io
            
            # Take full screenshot to memory
            screenshot_data = self.driver.get_screenshot_as_png()
            
            # Open with PIL
            image = Image.open(io.BytesIO(screenshot_data))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Find content boundaries by detecting non-white areas
            # Get image data as array
            import numpy as np
            img_array = np.array(image)
            
            # Find non-white pixels (allowing for slight variations)
            non_white_mask = np.any(img_array < 250, axis=2)  # RGB values less than 250
            
            # Find bounding box of non-white content
            rows = np.any(non_white_mask, axis=1)
            cols = np.any(non_white_mask, axis=0)
            
            if np.any(rows) and np.any(cols):
                top, bottom = np.where(rows)[0][[0, -1]]
                left, right = np.where(cols)[0][[0, -1]]
                
                # Add small padding
                padding = 5
                top = max(0, top - padding)
                left = max(0, left - padding)
                bottom = min(image.height, bottom + padding)
                right = min(image.width, right + padding)
                
                # Crop the image
                cropped = image.crop((left, top, right, bottom))
                
                # If we have expected dimensions and the cropped image is close, resize
                if expected_width and expected_height:
                    crop_width = right - left
                    crop_height = bottom - top
                    
                    # Check if dimensions are reasonably close (within 20%)
                    width_ratio = crop_width / expected_width
                    height_ratio = crop_height / expected_height
                    
                    if 0.8 <= width_ratio <= 1.2 and 0.8 <= height_ratio <= 1.2:
                        cropped = cropped.resize((expected_width, expected_height), Image.Resampling.LANCZOS)
                
                cropped.save(screenshot_file, 'PNG', optimize=True)
                self.logger.info(f"Cropped screenshot saved: {cropped.size}")
            else:
                # No content found, save original
                image.save(screenshot_file, 'PNG', optimize=True)
                self.logger.warning("No content detected for cropping, saved original")
                
        except ImportError:
            self.logger.warning("PIL not available for image processing, using fallback")
            if self.driver:
                self.driver.save_screenshot(str(screenshot_file))
        except Exception as e:
            self.logger.warning(f"Failed to crop screenshot: {e}")
            if self.driver:
                self.driver.save_screenshot(str(screenshot_file))

    def _generate_unique_filename(self, url: str) -> str:
        """
        Generate a unique filename from URL by hashing host+path+query.
        Preserves the original file extension if it exists.
        
        Args:
            url: The full URL to generate filename for
            
        Returns:
            Unique filename with original extension preserved
        """
        parsed = urlparse(url)
        
        # Create string to hash: host + path + query
        url_components = f"{parsed.netloc}{parsed.path}{parsed.query}"
        
        # Generate hash (first 12 characters should be enough for uniqueness)
        url_hash = hashlib.md5(url_components.encode('utf-8')).hexdigest()[:12]
        
        # Extract original extension from path
        original_ext = ''
        if parsed.path:
            path_parts = parsed.path.split('/')
            filename_part = path_parts[-1] if path_parts else ''
            if '.' in filename_part:
                original_ext = os.path.splitext(filename_part)[1]
        
        # Create unique filename: hash + original extension
        unique_filename = f"{url_hash}{original_ext}" if original_ext else url_hash
        
        return unique_filename

    def _cache_downloaded_asset(self, original_url: str, local_path: str) -> None:
        """
        Cache a downloaded asset mapping.
        
        Args:
            original_url: The original URL of the asset
            local_path: The local path where the asset was saved
        """
        # Normalize the original URL for consistent lookup
        original_url = original_url.strip()
        if original_url:
            self.asset_cache[original_url] = local_path
            self.logger.info(f"Cached asset: {original_url} -> {local_path}")

    def _get_local_asset_path(self, url: str, base_url: str = "") -> str:
        """
        Get the local path for a URL if it exists in cache, otherwise return the original URL.
        
        Args:
            url: The URL to check
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Local path if cached, otherwise original URL
        """
        if not url or url.startswith(('data:', 'javascript:', '#')):
            return url
            
        # Normalize URL for consistent cache lookup
        normalized_url = self._normalize_url(url, base_url if base_url else None)
        
        # Check if we have this URL cached
        if normalized_url in self.asset_cache:
            local_path = self.asset_cache[normalized_url]
            self.logger.info(f"Found cached asset: {normalized_url} -> {local_path}")
            return local_path
        
        # Not in cache, return original URL
        return url

    def _clear_asset_cache(self) -> None:
        """
        Clear the asset cache (useful between different banners).
        Note: In global assets mode, this only clears the in-memory cache,
        not the persistent global cache.
        """
        if self.global_assets:
            # Save current cache before clearing for next banner
            self._save_global_asset_cache()
            self.logger.info("Asset cache preserved in global storage")
        else:
            # In local mode, completely clear the cache
            self.asset_cache.clear()
            self.logger.info("Asset cache cleared")

    def _load_global_asset_cache(self) -> None:
        """
        Load the global asset cache from disk if it exists.
        """
        if not self.global_assets:
            return
            
        cache_file = self.global_assets_dir / 'asset_cache.json'
        if cache_file.exists():
            try:
                import json
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.asset_cache = json.load(f)
                self.logger.info(f"📂 Loaded {len(self.asset_cache)} assets from global cache")
            except Exception as e:
                self.logger.warning(f"Failed to load global asset cache: {e}")
                self.asset_cache = {}
        else:
            self.asset_cache = {}

    def _save_global_asset_cache(self) -> None:
        """
        Save the global asset cache to disk.
        """
        if not self.global_assets:
            return
            
        cache_file = self.global_assets_dir / 'asset_cache.json'
        try:
            import json
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.asset_cache, f, indent=2, ensure_ascii=False)
            self.logger.info(f"💾 Saved global asset cache with {len(self.asset_cache)} entries")
        except Exception as e:
            self.logger.warning(f"Failed to save global asset cache: {e}")

    def _get_asset_directory(self, banner_dir: Path) -> Path:
        """
        Get the appropriate assets directory based on global_assets setting.
        
        Args:
            banner_dir: The banner-specific directory
            
        Returns:
            Path to assets directory (either global or banner-specific)
        """
        if self.global_assets:
            return self.global_assets_dir
        else:
            assets_dir = banner_dir / 'assets'
            assets_dir.mkdir(exist_ok=True)
            return assets_dir

    def _get_asset_path_prefix(self) -> str:
        """
        Get the appropriate path prefix for assets in design data.
        
        Returns:
            Path prefix for asset references
        """
        if self.global_assets:
            return "../global_assets/"
        else:
            return "assets/"

    async def _download_asset_async(self, session: aiohttp.ClientSession, asset_url: str, 
                                   base_url: str, banner_dir: Path) -> Optional[str]:
        """
        Download an asset asynchronously and return the local filename.
        
        Args:
            session: aiohttp ClientSession
            asset_url: URL of the asset to download
            base_url: Base URL for resolving relative URLs
            banner_dir: Directory to save the asset
            
        Returns:
            Local filename if successful, None if failed
        """
        try:
            # Normalize URL for consistent handling and cache lookup
            full_url = self._normalize_url(asset_url, base_url)
            
            # Check cache first - if we already have this URL, return the cached path
            if full_url in self.asset_cache:
                cached_path = self.asset_cache[full_url]
                self.logger.info(f"Using cached asset: {full_url} -> {cached_path}")
                return cached_path
            
            # Generate unique filename using hash
            filename = self._generate_unique_filename(full_url)
            
            # Get appropriate assets directory and path prefix
            assets_dir = self._get_asset_directory(banner_dir)
            path_prefix = self._get_asset_path_prefix()
            
            # Generate unique filename if collision
            local_path = assets_dir / filename
            counter = 1
            base_name, ext = os.path.splitext(filename)
            while local_path.exists():
                filename = f"{base_name}_{counter}{ext}"
                local_path = assets_dir / filename
                counter += 1
            
            # Download the asset
            async with session.get(full_url) as response:
                # Debug logging for asset downloads
                self.logger.info(f"Downloading asset: {full_url}")
                self.logger.info(f"Response status: {response.status}")
                self.logger.info(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
                
                # Handle specific HTTP errors
                if response.status == 403:
                    self.logger.warning(f"403 Forbidden for asset {asset_url}")
                    self._record_download_failure()
                    return None
                elif response.status == 404:
                    self.logger.warning(f"404 Not Found for asset {asset_url}")
                    self._record_download_failure()
                    return None
                elif response.status == 429:
                    self.logger.warning(f"429 Rate Limited for asset {asset_url}")
                    self._record_download_failure()
                    return None
                
                response.raise_for_status()
                
                # Read content and validate it matches expected type
                content = await response.read()
                self.logger.info(f"Content length: {len(content)} bytes")
                
                # Validate content type matches expectation
                expected_type = self._get_expected_content_type(full_url)
                content_type_header = response.headers.get('content-type', '')
                
                if not self._validate_content_type(content, expected_type, content_type_header):
                    self.logger.warning(f"Content validation failed for {asset_url}")
                    self.logger.warning(f"Expected: {expected_type}, Content-Type: {content_type_header}")
                    self.logger.warning(f"Content preview: {content[:50]}")
                    self._record_download_failure()
                    return None
                
                self.logger.info(f"✅ Content validation passed: {expected_type} - {content_type_header}")
                
                # Write file asynchronously
                async with aiofiles.open(local_path, 'wb') as f:
                    await f.write(content)
                
                # Cache the downloaded asset with appropriate path prefix
                relative_path = f"{path_prefix}{filename}"
                self._cache_downloaded_asset(full_url, relative_path)
                
                self.logger.info(f"Downloaded asset: {filename} ({len(content)} bytes)")
                return relative_path
                
        except aiohttp.ClientError as e:
            self.logger.warning(f"HTTP error downloading asset {asset_url}: {e}")
            self._record_download_failure()
            return None
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout downloading asset {asset_url}")
            self._record_download_failure()
            return None
        except Exception as e:
            self.logger.warning(f"Failed to download asset {asset_url}: {e}")
            self._record_download_failure()
            return None

    async def _download_assets_parallel(self, asset_urls: List[str], base_url: str, 
                                       banner_dir: Path, max_concurrent: int = 5) -> Dict[str, str]:
        """
        Download multiple assets in parallel.
        
        Args:
            asset_urls: List of asset URLs to download
            base_url: Base URL for resolving relative URLs
            banner_dir: Directory to save assets
            max_concurrent: Maximum number of concurrent downloads
            
        Returns:
            Dictionary mapping original URLs to local paths
        """
        downloaded_assets = {}
        
        # Filter out data URLs and other non-downloadable URLs
        downloadable_urls = [
            url for url in asset_urls 
            if url and not url.startswith(('data:', 'javascript:', '#'))
        ]
        
        if not downloadable_urls:
            return downloaded_assets
        
        self.logger.info(f"Starting parallel download of {len(downloadable_urls)} assets...")
        
        async with await self._create_async_session(base_url) as session:
            # Create semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def download_with_semaphore(url: str) -> Tuple[str, Optional[str]]:
                async with semaphore:
                    result = await self._download_asset_async(session, url, base_url, banner_dir)
                    return url, result
            
            # Create tasks for all downloads
            tasks = [download_with_semaphore(url) for url in downloadable_urls]
            
            # Execute downloads with progress tracking
            completed = 0
            for coro in asyncio.as_completed(tasks):
                original_url, local_path = await coro
                completed += 1
                
                if local_path:
                    downloaded_assets[original_url] = local_path
                    self.logger.info(f"Progress: {completed}/{len(downloadable_urls)} - {original_url}")
                else:
                    self.logger.warning(f"Failed to download: {original_url}")
                
                # Progress update every 5 downloads or at completion
                if completed % 5 == 0 or completed == len(downloadable_urls):
                    self.logger.info(f"Downloaded {completed}/{len(downloadable_urls)} assets")
        
        # Save global cache if using global assets
        if self.global_assets:
            self._save_global_asset_cache()
        
        # Check if we have a reasonable success rate and record failures in global tracking
        failed_downloads = len(downloadable_urls) - len(downloaded_assets)
        if len(downloadable_urls) > 0:
            failure_rate = failed_downloads / len(downloadable_urls)
            self.logger.info(f"Parallel download completed: {len(downloaded_assets)} successful, {failed_downloads} failed (failure rate: {failure_rate*100:.1f}%)")
            
            # Record each failed download in the global failure tracking
            for _ in range(failed_downloads):
                self._record_download_failure()
        else:
            self.logger.info(f"Parallel download completed: {len(downloaded_assets)} successful downloads")
        
        return downloaded_assets

    def _download_asset(self, asset_url: str, base_url: str, banner_dir: Path) -> Optional[str]:
        """
        Download an asset (image, CSS, JS) and return the local filename.
        Uses the same cookies and headers as the Selenium session for authentication.
        
        Args:
            asset_url: URL of the asset to download
            base_url: Base URL for resolving relative URLs
            banner_dir: Directory to save the asset
            
        Returns:
            Local filename if successful, None if failed
        """

        

        try:
            # Normalize URL for consistent handling and cache lookup
            full_url = self._normalize_url(asset_url, base_url)
            
            # Check cache first - if we already have this URL, return the cached path
            if full_url in self.asset_cache:
                cached_path = self.asset_cache[full_url]
                self.logger.info(f"Using cached asset: {full_url} -> {cached_path}")
                return cached_path
            
            # Generate unique filename using hash
            filename = self._generate_unique_filename(full_url)
            
            # If no extension in filename, try to determine from content-type
            if '.' not in filename:
                try:
                    # Create session with Selenium cookies for authentication
                    session = requests.Session()
                    if self.driver:
                        # Get cookies from Selenium driver
                        selenium_cookies = self.driver.get_cookies()
                        for cookie in selenium_cookies:
                            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
                    
                    # Set browser-like headers
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': '*/*',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Referer': base_url
                    })
                    
                    head_response = session.head(full_url, timeout=5)
                    content_type = head_response.headers.get('content-type', '')
                    ext = mimetypes.guess_extension(content_type.split(';')[0])
                    if ext:
                        filename += ext
                except:
                    # Keep filename as-is if we can't determine content type
                    pass
            
            # Create assets directory
            assets_dir = self._get_asset_directory(banner_dir)
            
            # Generate unique filename if collision
            local_path = assets_dir / filename
            counter = 1
            base_name, ext = os.path.splitext(filename)
            while local_path.exists():
                filename = f"{base_name}_{counter}{ext}"
                local_path = assets_dir / filename
                counter += 1
            
            # Create session with Selenium cookies for authentication
            session = requests.Session()
            if self.driver:
                # Get cookies from Selenium driver
                selenium_cookies = self.driver.get_cookies()
                for cookie in selenium_cookies:
                    session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
            
            # Set browser-like headers to mimic the original request
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': base_url
            })
            
            # Download the asset with authentication
            response = session.get(full_url, timeout=10)
            
            # Debug logging for asset downloads
            self.logger.info(f"Downloading asset: {full_url}")
            self.logger.info(f"Response status: {response.status_code}")
            self.logger.info(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
            self.logger.info(f"Content length: {len(response.content)} bytes")
            
            # Handle specific HTTP errors with detailed logging
            if response.status_code == 403:
                self.logger.warning(f"403 Forbidden for asset {asset_url} - authentication/authorization issue")
                self._record_download_failure()
                return None
            elif response.status_code == 404:
                self.logger.warning(f"404 Not Found for asset {asset_url}")
                self._record_download_failure()
                return None
            elif response.status_code == 429:
                self.logger.warning(f"429 Rate Limited for asset {asset_url}")
                self._record_download_failure()
                return None
            
            response.raise_for_status()
            
            # Validate content type matches expectation
            expected_type = self._get_expected_content_type(full_url)
            content_type_header = response.headers.get('content-type', '')
            
            if not self._validate_content_type(response.content, expected_type, content_type_header):
                self.logger.warning(f"Content validation failed for {asset_url}")
                self.logger.warning(f"Expected: {expected_type}, Content-Type: {content_type_header}")
                self.logger.warning(f"Content preview: {response.content[:50]}")
                self._record_download_failure()
                return None
            
            self.logger.info(f"✅ Content validation passed: {expected_type} - {content_type_header}")
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            # Cache the downloaded asset with appropriate path prefix
            path_prefix = self._get_asset_path_prefix()
            relative_path = f"{path_prefix}{filename}"
            self._cache_downloaded_asset(full_url, relative_path)
            
            # Save global cache if using global assets
            if self.global_assets:
                self._save_global_asset_cache()
            
            self.logger.info(f"Downloaded asset: {filename} ({len(response.content)} bytes)")
            return relative_path
            
        except requests.exceptions.HTTPError as e:
            self.logger.warning(f"HTTP error downloading asset {asset_url}: {e}")
            self._record_download_failure()
            return None
        except requests.exceptions.Timeout:
            self.logger.warning(f"Timeout downloading asset {asset_url}")
            self._record_download_failure()
            return None
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Request error downloading asset {asset_url}: {e}")
            self._record_download_failure()
            return None
        except Exception as e:
            self.logger.warning(f"Failed to download asset {asset_url}: {e}")
            self._record_download_failure()
            return None

    def _normalize_urls_in_html(self, soup: BeautifulSoup, base_url: str, banner_dir: Path) -> Dict[str, str]:
        """
        Download assets and normalize URLs in HTML.
        
        Args:
            soup: BeautifulSoup object of the HTML
            base_url: Base URL for resolving relative URLs
            banner_dir: Directory to save assets
            
        Returns:
            Dictionary mapping original URLs to local paths
        """
        downloaded_assets = {}
       
        
        # Define URL attributes to process
        url_attributes = {
            'img': ['src', 'data-src'],
            'link': ['href'],
            'script': ['src'],
            'source': ['src'],
            'video': ['src', 'poster'],
            'audio': ['src'],
            'object': ['data'],
            'embed': ['src']
        }
        
        # Process each element type
        for tag_name, attributes in url_attributes.items():
            elements = soup.find_all(tag_name)
            for element in elements:
                # Only process Tag elements, not NavigableStrings
                if not isinstance(element, Tag):
                    continue
                
                # Skip stylesheet links - they're handled separately
                if tag_name == 'link':
                    rel_attr = element.get('rel')
                    if rel_attr and isinstance(rel_attr, (str, list)) and 'stylesheet' in (rel_attr if isinstance(rel_attr, list) else [rel_attr]):
                        continue
                
                for attr in attributes:
                    original_url = element.get(attr)
                    if isinstance(original_url, str) and original_url and not original_url.startswith(('data:', 'javascript:', '#')):
                        # Use normalized URL for consistent handling
                        full_url = self._normalize_url(original_url, base_url)
                        
                        # Download the asset
                        local_path = self._download_asset(full_url, base_url, banner_dir)
                        if local_path:
                            downloaded_assets[original_url] = local_path
                            # Update the element with local path
                            element[attr] = local_path
        
        # Process CSS files for @import and url() references
        css_links = soup.find_all('link', rel='stylesheet')
        for link in css_links:
            # Only process Tag elements, not NavigableStrings
            if not isinstance(link, Tag):
                continue
                
            href = link.get('href')
            if href and isinstance(href, str):
                # Handle absolute vs relative URLs for CSS
                if href.startswith(('http://', 'https://')):
                    css_url = href
                else:
                    css_url = urljoin(base_url, href)
                try:
                    # Create session with Selenium cookies for CSS download
                    session = requests.Session()
                    if self.driver:
                        # Get cookies from Selenium driver
                        selenium_cookies = self.driver.get_cookies()
                        for cookie in selenium_cookies:
                            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
                    
                    # Set browser-like headers
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/css,*/*;q=0.1',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Referer': base_url
                    })
                    
                    css_response = session.get(css_url, timeout=10)
                    
                    # Debug logging for CSS downloads
                    self.logger.info(f"Downloading CSS: {css_url}")
                    self.logger.info(f"CSS Response status: {css_response.status_code}")
                    self.logger.info(f"CSS Content-Type: {css_response.headers.get('content-type', 'unknown')}")
                    self.logger.info(f"CSS Content length: {len(css_response.content)} bytes")
                    
                    # Log first 200 chars of CSS content for debugging
                    css_preview = css_response.text[:200].replace('\n', ' ').replace('\r', ' ')
                    self.logger.info(f"CSS Content preview: {css_preview}...")
                    
                    css_response.raise_for_status()
                    css_content = css_response.text
                    
                    # Process CSS url() references
                    css_content = self._process_css_urls(css_content, css_url, banner_dir, downloaded_assets)
                    
                    # Save processed CSS using unique filename and appropriate directory
                    css_base_filename = self._generate_unique_filename(css_url)
                    # Ensure CSS extension if not present
                    if not css_base_filename.endswith('.css'):
                        css_base_filename += '.css'
                    
                    # Get appropriate assets directory and path prefix
                    assets_dir = self._get_asset_directory(banner_dir)
                    path_prefix = self._get_asset_path_prefix()
                    css_filename = f"{path_prefix}{css_base_filename}"
                    css_path = assets_dir / css_base_filename
                    
                    with open(css_path, 'w', encoding='utf-8') as f:
                        f.write(css_content)
                    
                    # Cache the CSS file
                    self._cache_downloaded_asset(css_url, css_filename)
                    link['href'] = css_filename
                    downloaded_assets[href] = css_filename
                    
                    # Save global cache if using global assets
                    if self.global_assets:
                        self._save_global_asset_cache()
                    
                except Exception as e:
                    self.logger.warning(f"Failed to process CSS file {css_url}: {e}")
        
        # Log success/failure summary (simple approach)
        self.logger.info(f"Sequential download completed: {len(downloaded_assets)} assets downloaded")
        
        return downloaded_assets

    def _collect_all_assets(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Dict[str, Any]]:
        """
        Collect all assets from HTML and CSS files in a single pass.
        Returns a unified asset collection with metadata for processing.
        
        Args:
            soup: BeautifulSoup object of the HTML
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary with asset info: {normalized_url: {type, original_url, element_refs, css_refs}}
        """
        all_assets = {}
        
        # Define URL attributes to process for HTML elements
        url_attributes = {
            'img': ['src', 'data-src'],
            'script': ['src'],
            'source': ['src'],
            'video': ['src', 'poster'],
            'audio': ['src'],
            'object': ['data'],
            'embed': ['src']
        }
        
        # Collect HTML-referenced assets
        for tag_name, attributes in url_attributes.items():
            elements = soup.find_all(tag_name)
            for element in elements:
                if not isinstance(element, Tag):
                    continue
                    
                for attr in attributes:
                    original_url = element.get(attr)
                    if isinstance(original_url, str) and original_url and not original_url.startswith(('data:', 'javascript:', '#')):
                        normalized_url = self._normalize_url(original_url, base_url)
                        
                        if normalized_url not in all_assets:
                            all_assets[normalized_url] = {
                                'type': 'html_asset',
                                'original_url': original_url,
                                'element_refs': [],
                                'css_refs': []
                            }
                        
                        all_assets[normalized_url]['element_refs'].append((element, attr, original_url))
        
        # Collect CSS files and their referenced assets
        css_links = soup.find_all('link', rel='stylesheet')
        for link in css_links:
            if not isinstance(link, Tag):
                continue
                
            href = link.get('href')
            if href and isinstance(href, str):
                css_url = self._normalize_url(href, base_url)
                
                # Add CSS file itself
                if css_url not in all_assets:
                    all_assets[css_url] = {
                        'type': 'css_file',
                        'original_url': href,
                        'element_refs': [(link, 'href', href)],
                        'css_refs': []
                    }
                
                # Try to fetch and parse CSS content for url() references
                try:
                    session = requests.Session()
                    if self.driver:
                        selenium_cookies = self.driver.get_cookies()
                        for cookie in selenium_cookies:
                            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
                    
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/css,*/*;q=0.1',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Referer': base_url
                    })
                    
                    css_response = session.get(css_url, timeout=10)
                    css_response.raise_for_status()
                    css_content = css_response.text
                    
                    # Store CSS content for later processing
                    all_assets[css_url]['css_content'] = css_content
                    
                    # Extract url() references from CSS
                    url_pattern = r'url\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)'
                    for match in re.finditer(url_pattern, css_content):
                        css_asset_url = match.group(1)
                        if not css_asset_url.startswith(('data:', '#')):
                            normalized_css_asset = self._normalize_url(css_asset_url, css_url)
                            
                            if normalized_css_asset not in all_assets:
                                all_assets[normalized_css_asset] = {
                                    'type': 'css_asset',
                                    'original_url': css_asset_url,
                                    'element_refs': [],
                                    'css_refs': []
                                }
                            
                            all_assets[normalized_css_asset]['css_refs'].append({
                                'css_url': css_url,
                                'original_css_asset_url': css_asset_url,
                                'match': match
                            })
                
                except Exception as e:
                    self.logger.warning(f"Failed to fetch CSS {css_url} for asset collection: {e}")
                    # Still add CSS file to assets even if content fetch failed
                    if css_url in all_assets:
                        all_assets[css_url]['css_content'] = None
        
        self.logger.info(f"Collected {len(all_assets)} unique assets from HTML and CSS")
        return all_assets

    async def _download_all_assets_unified(self, all_assets: Dict[str, Dict[str, Any]], 
                                         banner_dir: Path) -> Dict[str, str]:
        """
        Download all collected assets in a single unified parallel operation.
        
        Args:
            all_assets: Dictionary of all collected assets with metadata
            banner_dir: Directory to save assets
            
        Returns:
            Dictionary mapping original URLs to local paths
        """
        # Filter out assets that don't need downloading (data URLs, etc.)
        downloadable_assets = {}
        for normalized_url, asset_info in all_assets.items():
            if not normalized_url.startswith(('data:', 'javascript:', '#')):
                downloadable_assets[normalized_url] = asset_info
        
        if not downloadable_assets:
            self.logger.info("No assets to download")
            return {}
        
        self.logger.info(f"Starting unified download of {len(downloadable_assets)} unique assets...")
        
        # Download assets using existing parallel download method
        asset_urls = list(downloadable_assets.keys())
        
        # Use a dummy base_url since we're working with normalized URLs
        downloaded_assets = await self._download_assets_parallel(
            asset_urls, "", banner_dir, max_concurrent=5
        )
        
        self.logger.info(f"Unified download completed: {len(downloaded_assets)} assets downloaded")
        return downloaded_assets

    def _update_html_with_unified_assets(self, soup: BeautifulSoup, all_assets: Dict[str, Dict[str, Any]], 
                                       downloaded_assets: Dict[str, str], banner_dir: Path) -> Dict[str, str]:
        """
        Update HTML elements and CSS content with downloaded asset paths.
        
        Args:
            soup: BeautifulSoup object of the HTML
            all_assets: Dictionary of all collected assets with metadata
            downloaded_assets: Dictionary mapping URLs to local paths
            banner_dir: Directory containing assets
            
        Returns:
            Dictionary mapping original URLs to local paths (for compatibility)
        """
        result_mapping = {}
        
        # Update HTML elements
        for normalized_url, asset_info in all_assets.items():
            if normalized_url in downloaded_assets:
                local_path = downloaded_assets[normalized_url]
                
                # Update HTML element references
                for element, attr, original_url in asset_info['element_refs']:
                    element[attr] = local_path
                    result_mapping[original_url] = local_path
                
                # Handle CSS files - save processed content
                if asset_info['type'] == 'css_file' and 'css_content' in asset_info:
                    css_content = asset_info['css_content']
                    if css_content:
                        # Process CSS content to replace url() references
                        processed_css = self._update_css_urls(css_content, all_assets, downloaded_assets)
                        
                        # Save processed CSS file
                        css_filename = Path(local_path).name
                        assets_dir = self._get_asset_directory(banner_dir)
                        css_file_path = assets_dir / css_filename
                        
                        try:
                            with open(css_file_path, 'w', encoding='utf-8') as f:
                                f.write(processed_css)
                            self.logger.info(f"Saved processed CSS: {css_filename}")
                        except Exception as e:
                            self.logger.warning(f"Failed to save processed CSS {css_filename}: {e}")
        
        return result_mapping

    def _update_css_urls(self, css_content: str, all_assets: Dict[str, Dict[str, Any]], 
                        downloaded_assets: Dict[str, str]) -> str:
        """
        Update url() references in CSS content with local asset paths.
        
        Args:
            css_content: Original CSS content
            all_assets: Dictionary of all collected assets with metadata
            downloaded_assets: Dictionary mapping URLs to local paths
            
        Returns:
            Updated CSS content with local paths
        """
        def replace_url(match):
            original_url = match.group(1)
            if not original_url.startswith(('data:', '#')):
                # Find the normalized URL in our assets
                for normalized_url, asset_info in all_assets.items():
                    for css_ref in asset_info['css_refs']:
                        if css_ref['original_css_asset_url'] == original_url:
                            if normalized_url in downloaded_assets:
                                local_path = downloaded_assets[normalized_url]
                                return f'url("{local_path}")'
                            break
            return match.group(0)
        
        url_pattern = r'url\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)'
        return re.sub(url_pattern, replace_url, css_content)
        """
        Download assets and normalize URLs in HTML using parallel downloads.
        
        Args:
            soup: BeautifulSoup object of the HTML
            base_url: Base URL for resolving relative URLs
            banner_dir: Directory to save assets
            
        Returns:
            Dictionary mapping original URLs to local paths
        """
        # Collect all asset URLs first
        asset_urls = []
        elements_to_update = []  # Store (element, attr, original_url) for later updating
        
        # Define URL attributes to process
        url_attributes = {
            'img': ['src', 'data-src'],
            'script': ['src'],
            'source': ['src'],
            'video': ['src', 'poster'],
            'audio': ['src'],
            'object': ['data'],
            'embed': ['src']
        }
        
        # Collect all asset URLs (excluding CSS which needs special processing)
        for tag_name, attributes in url_attributes.items():
            elements = soup.find_all(tag_name)
            for element in elements:
                if not isinstance(element, Tag):
                    continue
                    
                for attr in attributes:
                    original_url = element.get(attr)
                    if isinstance(original_url, str) and original_url and not original_url.startswith(('data:', 'javascript:', '#')):
                        asset_urls.append(original_url)
                        elements_to_update.append((element, attr, original_url))
        
        # Download assets in parallel
        if asset_urls:
            self.logger.info(f"Downloading {len(asset_urls)} assets in parallel...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                downloaded_assets = loop.run_until_complete(
                    self._download_assets_parallel(asset_urls, base_url, banner_dir)
                )
            finally:
                loop.close()
            
            # Update elements with downloaded asset paths
            for element, attr, original_url in elements_to_update:
                # Handle absolute vs relative URLs for lookup
                if original_url.startswith(('http://', 'https://')):
                    lookup_url = original_url
                else:
                    lookup_url = urljoin(base_url, original_url)
                
                if lookup_url in downloaded_assets:
                    element[attr] = downloaded_assets[lookup_url]
        else:
            downloaded_assets = {}
        
        # Process CSS files separately (they need content processing) 
        css_links = soup.find_all('link', rel='stylesheet')
        css_tasks = []
        css_files_to_update = []
        
        for link in css_links:
            if not isinstance(link, Tag):
                continue
                
            href = link.get('href')
            if href and isinstance(href, str):
                # Use normalized URL for consistent CSS handling
                css_url = self._normalize_url(href, base_url)
                try:
                    # Create session with Selenium cookies for CSS download
                    session = requests.Session()
                    if self.driver:
                        selenium_cookies = self.driver.get_cookies()
                        for cookie in selenium_cookies:
                            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
                    
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/css,*/*;q=0.1',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Referer': base_url
                    })
                    
                    css_response = session.get(css_url, timeout=10)
                    
                    # Debug logging for CSS downloads
                    self.logger.info(f"Downloading CSS: {css_url}")
                    self.logger.info(f"CSS Response status: {css_response.status_code}")
                    self.logger.info(f"CSS Content-Type: {css_response.headers.get('content-type', 'unknown')}")
                    self.logger.info(f"CSS Content length: {len(css_response.content)} bytes")
                    
                    css_preview = css_response.text[:200].replace('\n', ' ').replace('\r', ' ')
                    self.logger.info(f"CSS Content preview: {css_preview}...")
                    
                    css_response.raise_for_status()
                    css_content = css_response.text
                    
                    # Prepare async CSS processing
                    task = self._process_css_urls_parallel(css_content, css_url, banner_dir, downloaded_assets)
                    css_tasks.append(task)
                    
                    # Save CSS file using unique filename and appropriate directory
                    css_base_filename = self._generate_unique_filename(css_url)
                    if not css_base_filename.endswith('.css'):
                        css_base_filename += '.css'
                    
                    assets_dir = self._get_asset_directory(banner_dir)
                    css_file = assets_dir / css_base_filename
                    css_files_to_update.append((css_file, link, css_content, css_url, href))
                    
                except Exception as e:
                    self.logger.warning(f"Failed to download CSS {css_url}: {e}")
        
        # Process all CSS files in parallel for url() references
        if css_tasks:
            self.logger.info(f"Processing {len(css_tasks)} CSS files for url() references in parallel...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                processed_css_contents = loop.run_until_complete(asyncio.gather(*css_tasks))
                
                # Save processed CSS files and update links
                for i, (css_file, link, original_css, css_url, href) in enumerate(css_files_to_update):
                    if i < len(processed_css_contents):
                        # Save processed CSS content
                        with open(css_file, 'w', encoding='utf-8') as f:
                            f.write(processed_css_contents[i])
                        
                        # Update link href and track asset
                        path_prefix = self._get_asset_path_prefix()
                        css_filename = f"{path_prefix}{css_file.name}"
                        
                        self._cache_downloaded_asset(css_url, css_filename)
                        link['href'] = css_filename
                        downloaded_assets[href] = css_filename
                        
                        if self.global_assets:
                            self._save_global_asset_cache()
            finally:
                loop.close()
        
        return downloaded_assets

    def _download_assets_with_retry(self, soup: BeautifulSoup, url: str, banner_dir: Path, max_retries: int = 3) -> bool:
        """
        Download assets with retry logic and exponential backoff.
        Validates that no download failures occurred to ensure project completeness.
        
        Args:
            soup: BeautifulSoup object of the HTML
            url: Base URL for resolving relative URLs
            banner_dir: Directory to save assets
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if assets downloaded without any failures, False otherwise
        """
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Downloading assets (attempt {attempt + 1}/{max_retries})...")
                
                # Reset failure tracking for each attempt
                self._reset_download_failure_tracking()
                
                if self.parallel_downloads:
                    self.logger.info("Using unified parallel download for all assets...")
                    # Collect all assets from HTML and CSS (keep original HTML unchanged)
                    soup_copy = copy.deepcopy(soup)  # Work with a copy to avoid modifying original during retries
                    all_assets = self._collect_all_assets(soup_copy, url)
                    
                    # Download all assets in a single unified operation
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        downloaded_assets_unified = loop.run_until_complete(
                            self._download_all_assets_unified(all_assets, banner_dir)
                        )
                    finally:
                        loop.close()
                    
                    # Only update HTML if download was successful enough
                    if len(downloaded_assets_unified) >= len(all_assets) * 0.8:  # 80% success threshold
                        downloaded_assets = self._update_html_with_unified_assets(
                            soup, all_assets, downloaded_assets_unified, banner_dir
                        )
                    else:
                        downloaded_assets = downloaded_assets_unified
                else:
                    self.logger.info("Using sequential download for assets...")
                    downloaded_assets = self._normalize_urls_in_html(soup, url, banner_dir)
                
                current_downloaded_count = len(downloaded_assets)
                
                # Check if any downloads failed during this attempt
                self.logger.info(f"DEBUG: _download_failures counter = {self._download_failures}")
                if hasattr(self, '_download_failures') and self._download_failures > 0:
                    raise Exception(f"❌ {self._download_failures} asset download(s) failed - project would be incomplete")
                
                if current_downloaded_count > 0:
                    self.logger.info(f"✅ All assets downloaded successfully: {current_downloaded_count} assets")
                    
                    # Save asset mapping
                    assets_file = banner_dir / 'assets.json'
                    with open(assets_file, 'w', encoding='utf-8') as f:
                        json.dump(downloaded_assets, f, indent=2)
                    
                    return True
                else:
                    # If no assets were found, that's actually fine - some banners might not have external assets
                    self.logger.info("No external assets found to download - banner is self-contained")
                    return True
                
            except Exception as e:
                self.logger.warning(f"Asset download attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^(attempt+1) seconds (2s, 4s, 8s...)
                    backoff_time = 2 ** (attempt + 1)
                    self.logger.info(f"Retrying asset download in {backoff_time} seconds...")
                    time.sleep(backoff_time)
                else:
                    self.logger.error(f"❌ All {max_retries} asset download attempts failed - project incomplete")
                    return False
        
        return False

    def _reset_download_failure_tracking(self):
        """Reset the download failure counter for a new attempt."""
        self._download_failures = 0

    def _record_download_failure(self):
        """Record a download failure."""
        if not hasattr(self, '_download_failures'):
            self._download_failures = 0
        self._download_failures += 1
        self.logger.warning(f"DEBUG: Download failure recorded. Total failures: {self._download_failures}")

    def _count_downloadable_assets(self, soup: BeautifulSoup) -> int:
        """
        Count the total number of downloadable assets in the HTML.
        Note: This only counts main assets, CSS url() references are counted separately during CSS processing.
        
        Args:
            soup: BeautifulSoup object of the HTML
            
        Returns:
            Total number of main assets that should be downloaded (excludes CSS url() references)
        """
        asset_count = 0
        
        # Define URL attributes to process
        url_attributes = {
            'img': ['src', 'data-src'],
            'link': ['href'],  # Will filter for non-stylesheet links
            'script': ['src'],
            'source': ['src'],
            'video': ['src', 'poster'],
            'audio': ['src'],
            'object': ['data'],
            'embed': ['src']
        }
        
        # Count downloadable assets
        for tag_name, attributes in url_attributes.items():
            elements = soup.find_all(tag_name)
            for element in elements:
                if not isinstance(element, Tag):
                    continue
                
                # Skip stylesheet links - they're handled separately with their own url() references
                if tag_name == 'link':
                    rel_attr = element.get('rel')
                    if rel_attr and isinstance(rel_attr, (str, list)) and 'stylesheet' in (rel_attr if isinstance(rel_attr, list) else [rel_attr]):
                        asset_count += 1  # Count the CSS file itself
                        continue
                
                for attr in attributes:
                    url = element.get(attr)
                    if isinstance(url, str) and url and not url.startswith(('data:', 'javascript:', '#')):
                        asset_count += 1
                        break  # Only count once per element
        
        return asset_count

    def _process_css_urls(self, css_content: str, css_base_url: str, banner_dir: Path, downloaded_assets: Dict[str, str]) -> str:
        """
        Process url() references in CSS content.
        
        Args:
            css_content: CSS content as string
            css_base_url: Base URL of the CSS file
            banner_dir: Directory to save assets
            downloaded_assets: Dictionary to track downloaded assets
            
        Returns:
            Processed CSS content with normalized URLs
        """
        # Pattern to match url() in CSS
        url_pattern = r'url\s*\(\s*["\']?([^"\')\s]+)["\']?\s*\)'
        
        def replace_url(match):
            original_url = match.group(1)
            # Skip data URLs, but process both absolute and relative URLs
            if not original_url.startswith(('data:', '#')):
                local_path = self._download_asset(original_url, css_base_url, banner_dir)
                if local_path:
                    downloaded_assets[original_url] = local_path
                    return f'url("{local_path}")'
            return match.group(0)
        
        return re.sub(url_pattern, replace_url, css_content)

    # OLD METHOD REMOVED: _process_css_urls_parallel
    # This functionality is now handled by the unified asset collection and download system
    
    def _extract_design_data(self, banner_dir: Path, size: str) -> Dict:
        """
        Extract comprehensive structured design data from the final animated state.
        Enhanced to better understand Google Web Designer structure and semantics.
        
        Args:
            banner_dir: Directory containing the banner
            size: Banner size (e.g., "300x600")
            
        Returns:
            Dictionary containing structured design data with semantic layers
        """
        if not self.driver:
            return {}
            
        try:
            # Extract data from the final animated state with enhanced GWD understanding
            design_data = self.driver.execute_script("""
                // Enhanced design data extraction with GWD semantics
                function extractEnhancedDesignData() {
                    const data = {
                        metadata: {
                            title: document.title || '',
                            size: arguments[0],
                            extractedAt: new Date().toISOString(),
                            url: window.location.href,
                            hasGWD: !!(window.gwd),
                            hasStudio: !!(window.studio),
                            hasEnabler: !!(window.Enabler),
                            timelineAvailable: !!(window.gwd && window.gwd.actions && window.gwd.actions.timeline),
                            animationLibraries: []
                        },
                        canvas: {
                            width: 0,
                            height: 0,
                            backgroundColor: 'transparent'
                        },
                        layers: [],
                        groups: {},
                        animations: [],
                        typography: {
                            fonts: new Set(),
                            colors: new Set(),
                            textElements: []
                        },
                        images: [],
                        interactions: [],
                        styles: {
                            keyframes: {}
                        }
                    };
                    
                    // Detect animation libraries and capabilities
                    if (window.gwd) data.metadata.animationLibraries.push('Google Web Designer');
                    if (window.gsap) data.metadata.animationLibraries.push('GSAP');
                    if (window.TweenMax) data.metadata.animationLibraries.push('TweenMax');
                    if (window.studio) data.metadata.animationLibraries.push('DoubleClick Studio');
                    
                    // Get canvas info from GWD page
                    const gwdPage = document.querySelector('gwd-page');
                    if (gwdPage) {
                        const pageRect = gwdPage.getBoundingClientRect();
                        const pageStyles = window.getComputedStyle(gwdPage);
                        data.canvas = {
                            width: pageRect.width,
                            height: pageRect.height,
                            backgroundColor: pageStyles.backgroundColor || 'transparent',
                            id: gwdPage.id,
                            classes: gwdPage.className
                        };
                    }
                    
                    // Collect groups first
                    const groupedElements = document.querySelectorAll('[data-gwd-group]');
                    groupedElements.forEach(el => {
                        const groupName = el.getAttribute('data-gwd-group');
                        if (!data.groups[groupName]) {
                            data.groups[groupName] = {
                                name: groupName,
                                elements: [],
                                boundingBox: null
                            };
                        }
                        
                        const rect = el.getBoundingClientRect();
                        data.groups[groupName].elements.push({
                            tagName: el.tagName.toLowerCase(),
                            id: el.id,
                            className: el.className,
                            position: { x: rect.left, y: rect.top, width: rect.width, height: rect.height },
                            content: el.textContent?.trim() || ''
                        });
                    });
                    
                    // Calculate bounding boxes for groups
                    Object.values(data.groups).forEach(group => {
                        if (group.elements.length > 0) {
                            const positions = group.elements.map(el => el.position);
                            const minX = Math.min(...positions.map(p => p.x));
                            const minY = Math.min(...positions.map(p => p.y));
                            const maxX = Math.max(...positions.map(p => p.x + p.width));
                            const maxY = Math.max(...positions.map(p => p.y + p.height));
                            
                            group.boundingBox = {
                                x: minX,
                                y: minY,
                                width: maxX - minX,
                                height: maxY - minY
                            };
                        }
                    });
                    
                    // Extract semantic layers - focus on meaningful content elements
                    const meaningfulElements = document.querySelectorAll([
                        'gwd-image', 'img',
                        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span',
                        'gwd-taparea',
                        '[class*="gwd-gen-"]', // Animated elements
                        '[id*="Heading"]', '[id*="heading"]',
                        '[id*="Logo"]', '[id*="logo"]',
                        '[id*="Button"]', '[id*="button"]', '[id*="CTA"]', '[id*="cta"]',
                        '[id*="Background"]', '[id*="background"]'
                    ].join(', '));
                    
                    meaningfulElements.forEach((element, index) => {
                        const rect = element.getBoundingClientRect();
                        const styles = window.getComputedStyle(element);
                        
                        // Skip if not visible or too small
                        if (rect.width < 1 || rect.height < 1 || 
                            styles.display === 'none' || 
                            styles.visibility === 'hidden' ||
                            parseFloat(styles.opacity) < 0.01) {
                            return;
                        }
                        
                        // Determine element type and semantic role
                        const className = typeof element.className === 'string' ? element.className : element.className.baseVal || '';
                        let elementType = 'unknown';
                        let semanticRole = 'decorative';
                        
                        if (element.tagName.toLowerCase() === 'gwd-image' || element.tagName.toLowerCase() === 'img') {
                            elementType = 'image';
                            if (element.id && (element.id.toLowerCase().includes('logo') || className.includes('logo'))) {
                                semanticRole = 'logo';
                            } else if (element.id && (element.id.toLowerCase().includes('background') || className.includes('background'))) {
                                semanticRole = 'background';
                            } else {
                                semanticRole = 'content-image';
                            }
                        } else if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(element.tagName.toLowerCase())) {
                            elementType = 'heading';
                            semanticRole = 'heading';
                        } else if (element.tagName.toLowerCase() === 'p') {
                            elementType = 'text';
                            if (element.id && (element.id.toLowerCase().includes('url') || element.textContent?.includes('www.'))) {
                                semanticRole = 'url';
                            } else {
                                semanticRole = 'body-text';
                            }
                        } else if (element.tagName.toLowerCase() === 'gwd-taparea') {
                            elementType = 'interaction';
                            semanticRole = 'clickable-area';
                        } else if (className.includes('gwd-gen-') || element.id?.toLowerCase().includes('cta') || element.id?.toLowerCase().includes('button')) {
                            elementType = 'interactive';
                            semanticRole = 'call-to-action';
                        }
                        
                        const layerData = {
                            id: element.id || `layer-${index}`,
                            type: elementType,
                            semanticRole: semanticRole,
                            tagName: element.tagName.toLowerCase(),
                            className: className,
                            position: {
                                x: Math.round(rect.left),
                                y: Math.round(rect.top),
                                width: Math.round(rect.width),
                                height: Math.round(rect.height),
                                zIndex: parseInt(styles.zIndex) || 0
                            },
                            styles: {
                                opacity: parseFloat(styles.opacity),
                                transform: styles.transform !== 'none' ? styles.transform : null,
                                backgroundColor: styles.backgroundColor,
                                color: styles.color,
                                fontSize: styles.fontSize,
                                fontFamily: styles.fontFamily,
                                fontWeight: styles.fontWeight,
                                textAlign: styles.textAlign,
                                backgroundImage: styles.backgroundImage !== 'none' ? styles.backgroundImage : null
                            },
                            content: {
                                text: element.textContent?.trim() || '',
                                src: element.src || null,
                                alt: element.alt || null
                            },
                            groupName: element.getAttribute('data-gwd-group'),
                            isAnimated: className.includes('gwd-gen-'),
                            animationInfo: null
                        };
                        
                        // Enhanced animation detection
                        if (layerData.isAnimated) {
                            const animationName = styles.animationName;
                            const animationDuration = styles.animationDuration;
                            const animationIterationCount = styles.animationIterationCount;
                            
                            layerData.animationInfo = {
                                name: animationName,
                                duration: animationDuration,
                                iterationCount: animationIterationCount,
                                timingFunction: styles.animationTimingFunction,
                                delay: styles.animationDelay,
                                fillMode: styles.animationFillMode
                            };
                            
                            data.animations.push({
                                elementId: layerData.id,
                                ...layerData.animationInfo
                            });
                        }
                        
                        // Collect typography info
                        if (elementType === 'heading' || elementType === 'text') {
                            data.typography.fonts.add(styles.fontFamily);
                            if (styles.color && styles.color !== 'rgba(0, 0, 0, 0)') {
                                data.typography.colors.add(styles.color);
                            }
                            
                            data.typography.textElements.push({
                                id: layerData.id,
                                text: layerData.content.text,
                                semanticRole: semanticRole,
                                typography: {
                                    fontFamily: styles.fontFamily,
                                    fontSize: styles.fontSize,
                                    fontWeight: styles.fontWeight,
                                    color: styles.color,
                                    textAlign: styles.textAlign,
                                    lineHeight: styles.lineHeight
                                }
                            });
                        }
                        
                        // Collect image info
                        if (elementType === 'image') {
                            data.images.push({
                                id: layerData.id,
                                src: layerData.content.src,
                                alt: layerData.content.alt,
                                semanticRole: semanticRole,
                                dimensions: {
                                    width: layerData.position.width,
                                    height: layerData.position.height
                                }
                            });
                        }
                        
                        // Collect interaction info
                        if (elementType === 'interaction' || semanticRole === 'call-to-action') {
                            data.interactions.push({
                                id: layerData.id,
                                type: semanticRole,
                                position: layerData.position,
                                content: layerData.content.text
                            });
                        }
                        
                        data.layers.push(layerData);
                    });
                    
                    // Sort layers by z-index and semantic importance
                    data.layers.sort((a, b) => {
                        // First by z-index
                        if (a.position.zIndex !== b.position.zIndex) {
                            return a.position.zIndex - b.position.zIndex;
                        }
                        // Then by semantic importance
                        const importance = {
                            'background': 0,
                            'decorative': 1,
                            'content-image': 2,
                            'body-text': 3,
                            'heading': 4,
                            'logo': 5,
                            'call-to-action': 6,
                            'clickable-area': 7
                        };
                        const aImportance = importance[a.semanticRole] || 1;
                        const bImportance = importance[b.semanticRole] || 1;
                        if (aImportance !== bImportance) {
                            return aImportance - bImportance;
                        }
                        // Finally by position
                        return a.position.y - b.position.y;
                    });
                    
                    // Convert Sets to Arrays for JSON serialization
                    data.typography.fonts = Array.from(data.typography.fonts);
                    data.typography.colors = Array.from(data.typography.colors);
                    
                    // Extract keyframes information
                    try {
                        const styleSheets = document.styleSheets;
                        for (let sheet of styleSheets) {
                            try {
                                for (let rule of sheet.cssRules || sheet.rules || []) {
                                    if (rule.type === CSSRule.KEYFRAMES_RULE || rule.type === 7) {
                                        data.styles.keyframes[rule.name] = {
                                            name: rule.name,
                                            rules: Array.from(rule.cssRules || []).map(keyframeRule => ({
                                                keyText: keyframeRule.keyText,
                                                style: keyframeRule.style.cssText
                                            }))
                                        };
                                    }
                                }
                            } catch (e) {
                                // Skip inaccessible stylesheets
                            }
                        }
                    } catch (e) {
                        // Error accessing stylesheets
                    }
                    
                    return data;
                }
                
                return extractEnhancedDesignData();
            """, size)
            
            self.logger.info(f"✅ Enhanced design data extracted:")
            self.logger.info(f"   📱 Canvas: {design_data.get('canvas', {}).get('width')}x{design_data.get('canvas', {}).get('height')}")
            self.logger.info(f"   🎨 Layers: {len(design_data.get('layers', []))}")
            self.logger.info(f"   👥 Groups: {len(design_data.get('groups', {}))}")
            self.logger.info(f"   🎬 Animations: {len(design_data.get('animations', []))}")
            self.logger.info(f"   🖼️ Images: {len(design_data.get('images', []))}")
            self.logger.info(f"   ✍️ Text elements: {len(design_data.get('typography', {}).get('textElements', []))}")
            self.logger.info(f"   🖱️ Interactions: {len(design_data.get('interactions', []))}")
            
            # Process URLs in extracted data to use local paths
            design_data = self._process_urls_in_design_data(design_data)
            
            return design_data
            
        except Exception as e:
            self.logger.warning(f"Failed to extract design data: {e}")
            return {}

    def _process_urls_in_design_data(self, design_data: Dict) -> Dict:
        """
        Process URLs in extracted design data to use local paths from cache.
        
        Args:
            design_data: Extracted design data containing URLs
            
        Returns:
            Design data with URLs converted to local paths where available
        """
        if not design_data:
            return design_data
            
        try:
            # Get the current page URL for resolving relative URLs
            current_url = design_data.get('metadata', {}).get('url', '')
            
            # Process layer data
            if 'layers' in design_data:
                for layer in design_data['layers']:
                    # Process src in content
                    if 'content' in layer and 'src' in layer['content'] and layer['content']['src']:
                        original_src = layer['content']['src']
                        local_path = self._get_local_asset_path(original_src, current_url)
                        if local_path != original_src:
                            self.logger.info(f"Converted layer src: {original_src} -> {local_path}")
                        layer['content']['src'] = local_path
                    
                    # Process backgroundImage in styles
                    if 'styles' in layer and 'backgroundImage' in layer['styles'] and layer['styles']['backgroundImage']:
                        bg_image = layer['styles']['backgroundImage']
                        # Extract URL from CSS url() function
                        if bg_image.startswith('url(') and bg_image.endswith(')'):
                            # Remove url() wrapper and quotes
                            url = bg_image[4:-1].strip('\'"')
                            local_path = self._get_local_asset_path(url, current_url)
                            if local_path != url:
                                layer['styles']['backgroundImage'] = f'url("{local_path}")'
                                self.logger.info(f"Converted layer backgroundImage: {url} -> {local_path}")
            
            # Process images data
            if 'images' in design_data:
                for image in design_data['images']:
                    if 'src' in image and image['src']:
                        original_src = image['src']
                        local_path = self._get_local_asset_path(original_src, current_url)
                        if local_path != original_src:
                            self.logger.info(f"Converted image src: {original_src} -> {local_path}")
                        image['src'] = local_path
            
            # Process interactions data (in case they have image URLs)
            if 'interactions' in design_data:
                for interaction in design_data['interactions']:
                    if 'src' in interaction and interaction['src']:
                        original_src = interaction['src']
                        local_path = self._get_local_asset_path(original_src, current_url)
                        if local_path != original_src:
                            self.logger.info(f"Converted interaction src: {original_src} -> {local_path}")
                        interaction['src'] = local_path
            
            self.logger.info(f"🔄 Processed URLs in design data using local asset cache")
            
            return design_data
            
        except Exception as e:
            self.logger.warning(f"Failed to process URLs in design data: {e}")
            return design_data

    def _wait_for_banner_load(self, driver: webdriver.Chrome, url: str) -> bool:
        """
        Wait for banner to fully load including animations.
        
        Args:
            driver: WebDriver instance
            url: Current URL
            
        Returns:
            True if banner loaded successfully
        """
        try:
            # Wait for basic page load
            WebDriverWait(driver, self.timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for Google Web Designer content
            time.sleep(3)
            
            # Check if page contains banner content
            body = driver.find_element(By.TAG_NAME, "body")
            if not body.text.strip() and not driver.find_elements(By.TAG_NAME, "img"):
                self.logger.warning(f"Page appears empty: {url}")
                return False
            
            # Wait a bit more for animations to start
            time.sleep(2)
            
            return True
            
        except TimeoutException:
            self.logger.warning(f"Timeout waiting for page load: {url}")
            return False
        except Exception as e:
            self.logger.error(f"Error waiting for banner load: {e}")
            return False
    
    def scrape_banner(self, url: str, banner_id: str, size: str) -> bool:
        """
        Scrape a single banner URL.
        
        Args:
            url: Banner URL
            banner_id: Banner identifier
            size: Banner size
            
        Returns:
            True if scraping was successful
        """
        try:
            self.logger.info(f"Scraping banner: {banner_id} ({size}) - {url}")
            
            # Clear asset cache for new banner
            self._clear_asset_cache()
            
            # Ensure driver is available
            if not self.driver:
                self.logger.error("Driver not initialized")
                self.stats['failed'] += 1
                return False
            
            # Create directory structure
            banner_dir = self.output_dir / banner_id / size
            banner_dir.mkdir(parents=True, exist_ok=True)
            
            # Navigate to URL
            self.driver.get(url)
            
            # Wait for banner to load
            if not self._wait_for_banner_load(self.driver, url):
                self.stats['failed'] += 1
                return False
            
            # Take screenshot FIRST - before any modifications to the page
            if self.screenshot:
                screenshot_file = banner_dir / 'screenshot.png'
                try:
                    self.logger.info("Taking screenshot of original banner state...")
                    self._take_banner_screenshot(screenshot_file, size)
                    self.logger.info(f"Screenshot saved: {screenshot_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to take screenshot: {e}")
            
            # Get page source AFTER screenshot
            html_content = self.driver.page_source
            
            # Parse with BeautifulSoup for cleaning
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Download assets with retry logic - DON'T save index.html until this succeeds
            assets_downloaded = False
            try:
                self.logger.info("Downloading assets and normalizing URLs...")
                assets_downloaded = self._download_assets_with_retry(soup, url, banner_dir)
                
                if not assets_downloaded:
                    self.logger.error("Failed to download assets after retries - banner incomplete")
                    self.stats['failed'] += 1
                    return False
                    
            except Exception as e:
                self.logger.error(f"Failed to download assets: {e}")
                self.stats['failed'] += 1
                return False
            
            # Only save index.html if assets were successfully downloaded
            html_file = banner_dir / 'index.html'
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(str(soup.prettify()))
            
            # Extract structured design data from final animated state
            try:
                self.logger.info("Extracting structured design data...")
                design_data = self._extract_design_data(banner_dir, size)
                
                if design_data:
                    design_file = banner_dir / 'design_data.json'
                    with open(design_file, 'w', encoding='utf-8') as f:
                        json.dump(design_data, f, indent=2)
                    
                    self.logger.info(f"Design data extracted: {len(design_data.get('elements', []))} elements")
                else:
                    self.logger.warning("No design data extracted")
                    
            except Exception as e:
                self.logger.warning(f"Failed to extract design data: {e}")
            
            # Save metadata
            metadata = {
                'url': url,
                'banner_id': banner_id,
                'size': size,
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'title': self.driver.title or '',
                'has_animations': 'gwd' in html_content.lower() or 'studio' in html_content.lower()
            }
            
            metadata_file = banner_dir / 'metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            self.logger.info(f"Successfully scraped: {banner_id} ({size})")
            self.stats['successful'] += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {e}")
            self.stats['failed'] += 1
            return False
    
    def load_design_urls(self, json_file: str) -> List[Dict]:
        """
        Load banner URLs from JSON file.
        
        Args:
            json_file: Path to JSON file containing banner data
            
        Returns:
            List of banner configurations
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            banners = []
            for item in data:
                if isinstance(item, dict) and 'id' in item and 'sizes' in item:
                    for size_info in item['sizes']:
                        if isinstance(size_info, dict) and 'url' in size_info:
                            banners.append({
                                'id': item['id'],
                                'size': size_info.get('name', 'unknown'),
                                'url': size_info['url']
                            })
            
            self.logger.info(f"Loaded {len(banners)} banner URLs from {json_file}")
            return banners
            
        except Exception as e:
            self.logger.error(f"Failed to load JSON file {json_file}: {e}")
            return []
    
    def run(self, json_file: str, max_banners: Optional[int] = None, 
            start_from: int = 0, sizes: Optional[List[str]] = None) -> None:
        """
        Run the scraping process.
        
        Args:
            json_file: Path to JSON file with banner URLs
            max_banners: Maximum number of banners to scrape
            start_from: Index to start scraping from
            sizes: List of specific sizes to filter by (e.g., ['300x250', '728x90'])
        """
        try:
            # Load banner URLs
            banners = self.load_design_urls(json_file)
            if not banners:
                self.logger.error("No banners loaded. Exiting.")
                return
            
            # Apply size filter if specified
            if sizes:
                original_count = len(banners)
                banners = [banner for banner in banners if banner['size'] in sizes]
                self.logger.info(f"Size filter applied: {len(banners)}/{original_count} banners match sizes {sizes}")
                
                if not banners:
                    self.logger.warning("No banners match the specified sizes. Available sizes:")
                    available_sizes = set(banner['size'] for banner in self.load_design_urls(json_file))
                    for size in sorted(available_sizes):
                        self.logger.info(f"  - {size}")
                    return
            
            # Apply filters
            if start_from > 0:
                banners = banners[start_from:]
                self.logger.info(f"Starting from index {start_from}")
            
            if max_banners:
                banners = banners[:max_banners]
                self.logger.info(f"Limited to {max_banners} banners")
            
            self.stats['total_urls'] = len(banners)
            
            # Setup driver
            self.driver = self._setup_driver()
            self.logger.info("WebDriver initialized successfully")
            
            # Process banners
            for i, banner in enumerate(banners, 1):
                self.logger.info(f"Processing {i}/{len(banners)}: {banner['id']} ({banner['size']})")
                
                # Check if already scraped (unless force flag is set)
                output_path = self.output_dir / banner['id'] / banner['size'] / 'index.html'
                if output_path.exists() and not self.force:
                    self.logger.info(f"Already scraped: {banner['id']} ({banner['size']})")
                    self.stats['skipped'] += 1
                    continue
                elif output_path.exists() and self.force:
                    self.logger.info(f"Force re-scraping: {banner['id']} ({banner['size']})")
                
                # Scrape banner
                # URL encode the URL to handle special characters
                
                success = self.scrape_banner(banner['url'], banner['id'], banner['size'])
                
                # Small delay between requests
                time.sleep(1)
                
                # Progress update every 10 banners
                if i % 10 == 0:
                    self._print_progress()
            
            self._print_final_stats()
            
        except KeyboardInterrupt:
            self.logger.info("Scraping interrupted by user")
            self._print_final_stats()
        except Exception as e:
            self.logger.error(f"Unexpected error during scraping: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver closed")
    
    def _print_progress(self):
        """Print current progress statistics."""
        total = self.stats['total_urls']
        completed = self.stats['successful'] + self.stats['failed'] + self.stats['skipped']
        success_rate = (self.stats['successful'] / max(completed, 1)) * 100
        
        self.logger.info(
            f"Progress: {completed}/{total} completed "
            f"({success_rate:.1f}% success rate) - "
            f"Success: {self.stats['successful']}, "
            f"Failed: {self.stats['failed']}, "
            f"Skipped: {self.stats['skipped']}"
        )
    
    def _print_final_stats(self):
        """Print final scraping statistics."""
        self.logger.info("=" * 50)
        self.logger.info("SCRAPING COMPLETED")
        self.logger.info("=" * 50)
        self.logger.info(f"Total URLs: {self.stats['total_urls']}")
        self.logger.info(f"Successful: {self.stats['successful']}")
        self.logger.info(f"Failed: {self.stats['failed']}")
        self.logger.info(f"Skipped: {self.stats['skipped']}")
        
        if self.stats['total_urls'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total_urls']) * 100
            self.logger.info(f"Success Rate: {success_rate:.1f}%")
        
        self.logger.info(f"Output Directory: {self.output_dir.absolute()}")
        self.logger.info("=" * 50)


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Scrape HTML5 banner designs')
    parser.add_argument('json_file', nargs='?', default='../frontend/public/htmldesigns.json',
                       help='Path to JSON file with banner URLs')
    parser.add_argument('--output-dir', default='scraped_banners',
                       help='Output directory for scraped content')
    parser.add_argument('--no-headless', action='store_true',
                       help='Run browser in non-headless mode')
    parser.add_argument('--screenshot', action='store_true',
                       help='Take screenshots of banners')
    parser.add_argument('--timeout', type=int, default=15,
                       help='Timeout for page loads in seconds')
    parser.add_argument('--max-banners', type=int,
                       help='Maximum number of banners to scrape')
    parser.add_argument('--start-from', type=int, default=0,
                       help='Index to start scraping from')
    parser.add_argument('--sizes', nargs='+', 
                       help='Filter by specific banner sizes (e.g., --sizes 300x250 728x90)')
    parser.add_argument('--keep-animations', action='store_true',
                       help='Keep animations looping (may cause incomplete screenshots)')
    parser.add_argument('--global-assets', action='store_true',
                       help='Download assets to global directory for reuse across projects')
    parser.add_argument('--no-parallel', action='store_true',
                       help='Disable parallel asset downloads (use sequential downloads)')
    parser.add_argument('--force', action='store_true',
                       help='Force re-scraping of already scraped projects instead of skipping them')
    
    args = parser.parse_args()
    
    # Create scraper instance
    scraper = HTMLBannerScraper(
        output_dir=args.output_dir,
        headless=not args.no_headless,
        timeout=args.timeout,
        screenshot=args.screenshot,
        control_animations=not args.keep_animations,
        global_assets=args.global_assets,
        parallel_downloads=not args.no_parallel,
        force=args.force
    )
    
    # Run scraping
    scraper.run(args.json_file, args.max_banners, args.start_from, args.sizes)


if __name__ == '__main__':
    main()
