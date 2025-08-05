# API Reference Documentation

This document provides a comprehensive reference for the GWD Banner Processing System's core classes and methods.

## 📚 Core Classes

### BannerScraper Class

The main class responsible for scraping and processing GWD banners.

```python
class BannerScraper:
    def __init__(self, width_filter=None, max_width=None, height_filter=None, 
                 max_height=None, save_screenshots=True, download_assets=True,
                 debug=False)
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width_filter` | int | None | Exact width filter (e.g., 300) |
| `max_width` | int | None | Maximum width threshold |
| `height_filter` | int | None | Exact height filter (e.g., 600) |
| `max_height` | int | None | Maximum height threshold |
| `save_screenshots` | bool | True | Enable screenshot capture |
| `download_assets` | bool | True | Download banner assets |
| `debug` | bool | False | Enable debug output |

#### Example Usage

```python
# Basic scraper
scraper = BannerScraper()

# Filter for mobile banners (320x50)
scraper = BannerScraper(width_filter=320, height_filter=50)

# Limit to small banners only
scraper = BannerScraper(max_width=400, max_height=400)

# Screenshots only, no asset download
scraper = BannerScraper(download_assets=False)
```

### Public Methods

#### `scrape_banners(urls, start_index=0)`

Main method to process a list of banner URLs.

```python
def scrape_banners(self, urls: List[str], start_index: int = 0) -> Dict
```

**Parameters:**
- `urls` (List[str]): List of banner URLs to process
- `start_index` (int): Starting index for processing (default: 0)

**Returns:**
- `Dict`: Processing results with success/failure counts

**Example:**
```python
urls = [
    "https://example.com/banner1/index.html",
    "https://example.com/banner2/index.html"
]
results = scraper.scrape_banners(urls, start_index=0)
print(f"Processed: {results['successful']}, Failed: {results['failed']}")
```

#### `get_banner_size(url)`

Extract banner dimensions from URL.

```python
def get_banner_size(self, url: str) -> Tuple[int, int]
```

**Parameters:**
- `url` (str): Banner URL to analyze

**Returns:**
- `Tuple[int, int]`: Width and height in pixels

**Example:**
```python
width, height = scraper.get_banner_size("https://example.com/300x250/index.html")
print(f"Banner size: {width}x{height}")  # Output: Banner size: 300x250
```

#### `should_skip_banner(width, height)`

Check if banner should be skipped based on size filters.

```python
def should_skip_banner(self, width: int, height: int) -> bool
```

**Parameters:**
- `width` (int): Banner width in pixels
- `height` (int): Banner height in pixels

**Returns:**
- `bool`: True if banner should be skipped

**Example:**
```python
# For scraper with max_width=400
should_skip = scraper.should_skip_banner(728, 90)  # Returns True
should_skip = scraper.should_skip_banner(300, 250)  # Returns False
```

### Private Methods (Internal Use)

#### `_setup_driver()`

Initialize Chrome WebDriver with optimal settings.

```python
def _setup_driver(self) -> webdriver.Chrome
```

**Returns:**
- `webdriver.Chrome`: Configured Chrome driver instance

**Configuration:**
- Headless mode enabled
- Window size: 1920x1080
- User agent spoofing
- Various Chrome options for stability

#### `_take_screenshot(driver, url, width, height)`

Capture banner screenshot with proper timing.

```python
def _take_screenshot(self, driver: webdriver.Chrome, url: str, 
                    width: int, height: int) -> str
```

**Parameters:**
- `driver`: WebDriver instance
- `url`: Banner URL
- `width`: Banner width
- `height`: Banner height

**Returns:**
- `str`: Screenshot filename (MD5 hash based)

**Features:**
- Waits for page load and animations
- Sets proper viewport size
- Generates unique filenames
- Handles animation completion

#### `_extract_design_data(driver, url, width, height)`

Extract comprehensive design data using semantic analysis.

```python
def _extract_design_data(self, driver: webdriver.Chrome, url: str, 
                        width: int, height: int) -> Dict
```

**Parameters:**
- `driver`: WebDriver instance
- `url`: Banner URL
- `width`: Banner width
- `height`: Banner height

**Returns:**
- `Dict`: Structured design data

**Extraction Features:**
- Semantic element classification
- Animation timeline analysis
- Typography extraction
- Color palette detection
- Asset URL resolution
- Interactive element mapping

#### `_download_assets(driver, design_data, width, height)`

Download all banner assets with authentication.

```python
def _download_assets(self, driver: webdriver.Chrome, design_data: Dict, 
                    width: int, height: int) -> None
```

**Parameters:**
- `driver`: WebDriver instance
- `design_data`: Extracted design data
- `width`: Banner width
- `height`: Banner height

**Features:**
- Session cookie preservation
- Absolute URL resolution
- Unique filename generation
- Error handling for missing assets

## 🛠️ Utility Functions

### `create_unique_filename(url, original_filename)`

Generate unique filenames using MD5 hashing.

```python
def create_unique_filename(url: str, original_filename: str) -> str
```

**Parameters:**
- `url` (str): Source URL for hash generation
- `original_filename` (str): Original asset filename

**Returns:**
- `str`: Unique filename with preserved extension

**Example:**
```python
filename = create_unique_filename(
    "https://example.com/image.jpg", 
    "image.jpg"
)
# Returns: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6.jpg"
```

### `extract_banner_info(url)`

Parse banner dimensions and info from URL.

```python
def extract_banner_info(url: str) -> Dict
```

**Parameters:**
- `url` (str): Banner URL to parse

**Returns:**
- `Dict`: Banner information including dimensions

**Example:**
```python
info = extract_banner_info("https://example.com/campaigns/300x250/index.html")
# Returns: {"width": 300, "height": 250, "size": "300x250"}
```

## 🔧 Configuration Options

### WebDriver Configuration

Default Chrome options used for optimal banner processing:

```python
chrome_options = [
    "--headless",
    "--no-sandbox", 
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-plugins",
    "--disable-images",  # Disabled for faster loading
    "--window-size=1920,1080",
    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
]
```

### Timing Configuration

Critical timing values for proper banner capture:

```python
WAIT_TIMES = {
    'page_load': 3,      # Initial page load wait
    'animation': 2,      # Animation completion wait
    'screenshot': 1,     # Pre-screenshot stabilization
    'asset_load': 0.5    # Between asset downloads
}
```

### File Output Configuration

Output directory structure:

```
output/
├── screenshots/          # Banner screenshots
├── assets/              # Downloaded assets
│   ├── 300x250/        # Size-specific directories
│   └── 728x90/
└── data/               # JSON data files
    ├── htmldesigns.json # Main design data
    └── individual/     # Per-banner JSON files
```

## 🚀 Performance Optimization

### Memory Management

```python
# Driver cleanup after each banner
def cleanup_driver(self):
    if self.driver:
        self.driver.quit()
        self.driver = None
```

### Batch Processing

```python
# Process banners in batches
def process_batch(urls, batch_size=10):
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i + batch_size]
        scraper = BannerScraper()
        scraper.scrape_banners(batch)
        scraper.cleanup_driver()  # Clean up between batches
```

### Asset Optimization

```python
# Skip duplicate asset downloads
def is_asset_downloaded(url, filename):
    return os.path.exists(f"output/assets/{filename}")
```

## 🔍 Error Handling

### Exception Types

| Exception | Description | Handling |
|-----------|-------------|----------|
| `TimeoutException` | Page load timeout | Skip banner, log error |
| `WebDriverException` | Driver issues | Restart driver |
| `requests.RequestException` | Asset download failure | Log, continue processing |
| `JSONDecodeError` | Invalid JSON data | Use fallback data structure |

### Error Recovery

```python
try:
    self._process_banner(url)
except TimeoutException:
    logger.warning(f"Timeout processing {url}")
    self.stats['timeouts'] += 1
except Exception as e:
    logger.error(f"Error processing {url}: {e}")
    self.stats['errors'] += 1
finally:
    # Always cleanup
    self._reset_driver_state()
```

## 📊 Return Data Formats

### Processing Results

```python
{
    "total_processed": 150,
    "successful": 142,
    "failed": 8,
    "skipped": 25,
    "timeouts": 3,
    "errors": 5,
    "processing_time": "00:45:32"
}
```

### Design Data Structure

See [Structured Data Schema](structured_data_schema.md) for complete format reference.

## 🔄 Version Compatibility

- **Python**: 3.8+
- **Selenium**: 4.0+
- **Chrome**: Latest stable
- **ChromeDriver**: Auto-managed by Selenium

## 📋 Best Practices

1. **Resource Management**: Always cleanup WebDriver instances
2. **Error Handling**: Implement comprehensive exception handling
3. **Batch Processing**: Process large URL lists in batches
4. **Memory Monitoring**: Monitor memory usage for large datasets
5. **Asset Management**: Implement deduplication for assets
6. **Logging**: Use structured logging for debugging
7. **Validation**: Validate banner sizes before processing
8. **Recovery**: Implement graceful recovery from failures
