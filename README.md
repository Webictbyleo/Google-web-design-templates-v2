# Google Web Designer (GWD) Banner Processing System

A comprehensive system for scraping, analyzing, and extracting structured data from HTML5 banners created with Google Web Designer.

## 📁 Directory Structure

```
gwd/
├── scripts/                 # Core processing scripts
│   ├── html_banner_scraper.py    # Main banner scraper
│   ├── list_banner_sizes.py      # Banner size utility
│   └── verify_screenshots.py     # Screenshot verification
├── data/                    # Input data and configurations
│   ├── htmldesigns.json          # Main banner URL database
│   └── test_banner.json          # Test configuration
├── docs/                    # Documentation
│   ├── README.md                 # This file
│   ├── structured_data_schema.md # Data structure documentation
│   └── api_reference.md          # API documentation
└── output/                  # Generated output (scraped banners)
    └── scraped_banners/          # Default output directory
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Chrome/Chromium browser
- Required Python packages:
  ```bash
  pip install selenium beautifulsoup4 pillow numpy requests
  ```

### Basic Usage

```bash
cd gwd/scripts
python html_banner_scraper.py ../data/htmldesigns.json --screenshot --max-banners 5
```

### Advanced Usage

```bash
# Scrape specific banner sizes
python html_banner_scraper.py ../data/htmldesigns.json --sizes 300x600 728x90 --screenshot

# Run in non-headless mode for debugging
python html_banner_scraper.py ../data/htmldesigns.json --no-headless --screenshot

# Custom output directory
python html_banner_scraper.py ../data/htmldesigns.json --output-dir custom_output --screenshot
```

## 📊 What the System Captures

### 1. **Visual Assets**
- 📸 **Screenshots**: Clean, properly composed images captured before any modifications
- 🖼️ **Images**: All banner images with unique hash-based filenames
- 🎨 **Fonts**: Complete font files for offline rendering
- 📱 **CSS**: Normalized stylesheets with local asset references

### 2. **Structured Design Data**
- 🎯 **Semantic Layers**: Logo, headings, body text, call-to-action elements
- 🎬 **Animation Timeline**: Complete animation sequences with timing
- 🎨 **Typography**: Fonts, colors, sizes, and text styling
- 📐 **Layout**: Positions, dimensions, and z-index hierarchy
- 🖱️ **Interactions**: Clickable areas and interactive elements

### 3. **Technical Metadata**
- 🏗️ **Canvas Information**: Banner dimensions and properties
- 👥 **Group Structure**: GWD groups and element relationships
- 🔗 **Asset Mapping**: Original URLs to local file mapping
- ⚙️ **Animation Details**: Keyframes, timing functions, and delays

## 🏗️ Output Structure

Each processed banner creates this structure:

```
output/scraped_banners/
└── {banner_id}/
    └── {size}/
        ├── index.html          # Self-contained HTML with normalized assets
        ├── screenshot.png      # Clean banner screenshot
        ├── design_data.json    # Comprehensive structured data
        ├── assets.json         # Asset URL mapping
        ├── metadata.json       # Basic banner metadata
        └── assets/             # All downloaded assets
            ├── {hash}.png      # Images with unique names
            ├── {hash}.css      # Stylesheets
            ├── {hash}.js       # JavaScript files
            └── {hash}.woff2    # Font files
```

## 📋 Command Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--screenshot` | Take screenshots of banners | `--screenshot` |
| `--max-banners N` | Limit number of banners to process | `--max-banners 10` |
| `--sizes` | Filter by specific banner sizes | `--sizes 300x600 728x90` |
| `--start-from N` | Start from specific index | `--start-from 50` |
| `--output-dir` | Custom output directory | `--output-dir my_output` |
| `--no-headless` | Show browser window (debugging) | `--no-headless` |
| `--timeout N` | Page load timeout in seconds | `--timeout 30` |
| `--keep-animations` | Don't control animations | `--keep-animations` |

## 🎯 Key Features

### Semantic Understanding
- **Logo Detection**: Automatically identifies brand logos
- **CTA Recognition**: Finds call-to-action buttons and areas
- **Content Classification**: Distinguishes headings, body text, URLs
- **Layout Analysis**: Understands visual hierarchy and relationships

### Animation Intelligence
- **Timeline Control**: Lets animations complete once before capturing
- **Keyframe Extraction**: Captures detailed animation data
- **Timing Analysis**: Records delays, durations, and easing functions
- **State Capture**: Screenshots taken at optimal animation state

### Asset Management
- **Session Authentication**: Uses browser cookies for protected assets
- **Unique Naming**: MD5 hash-based filenames prevent collisions
- **URL Normalization**: Converts to local references for offline use
- **Complete Preservation**: Downloads all images, fonts, CSS, JS

### Quality Assurance
- **Error Handling**: Graceful degradation for various failure scenarios
- **Comprehensive Logging**: Detailed progress tracking and diagnostics
- **Validation**: Verifies screenshot quality and asset completeness
- **Retry Logic**: Handles temporary network issues

## 🔧 Utilities

### Banner Size Analysis
```bash
python list_banner_sizes.py ../data/htmldesigns.json
```

### Screenshot Verification
```bash
python verify_screenshots.py ../output/scraped_banners
```

## 📈 Performance Metrics

The system provides detailed statistics:
- **Success Rate**: Percentage of successfully processed banners
- **Asset Coverage**: Number of assets downloaded per banner
- **Processing Speed**: Time per banner with breakdown
- **Error Analysis**: Categorized failure reasons

## 🐛 Troubleshooting

### Common Issues

1. **Browser Not Found**
   ```bash
   # Install Chrome/Chromium
   sudo apt-get install chromium-browser
   ```

2. **Permission Errors**
   ```bash
   # Fix output directory permissions
   chmod 755 -R ../output/
   ```

3. **Network Timeouts**
   ```bash
   # Increase timeout
   python html_banner_scraper.py --timeout 60
   ```

### Debug Mode
Run with `--no-headless` to see browser actions:
```bash
python html_banner_scraper.py ../data/test_banner.json --no-headless --screenshot
```

## 📚 Related Documentation

- [Structured Data Schema](structured_data_schema.md) - Complete data format documentation
- [API Reference](api_reference.md) - Programming interface details
- [Best Practices](best_practices.md) - Optimization and usage guidelines

## 🎯 Use Cases

1. **Design Analysis**: Understanding banner composition and trends
2. **Asset Extraction**: Getting high-quality assets from existing banners
3. **Template Creation**: Building reusable banner templates
4. **Quality Assurance**: Verifying banner rendering across platforms
5. **Competitive Analysis**: Studying successful banner designs
6. **Archive Creation**: Preserving banner campaigns for reference

## 🚀 Future Enhancements

- [ ] Multi-format export (PDF, SVG, Figma)
- [ ] Automated A/B testing data extraction
- [ ] Banner performance metrics integration
- [ ] Real-time banner monitoring
- [ ] Machine learning-based design analysis
