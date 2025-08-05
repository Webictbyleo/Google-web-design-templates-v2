#!/usr/bin/env python3
"""
Banner Size Lister

This utility script lists all available banner sizes from the htmldesigns.json file.
Useful for determining what sizes to filter by when using the scraper.

Usage:
    python list_banner_sizes.py [json_file]
"""

import json
import sys
from collections import Counter
from pathlib import Path


def list_banner_sizes(json_file: str = '../frontend/public/htmldesigns.json'):
    """
    List all available banner sizes from the JSON file.
    
    Args:
        json_file: Path to the JSON file containing banner data
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        sizes = []
        banner_count = 0
        
        for item in data:
            if isinstance(item, dict) and 'id' in item and 'sizes' in item:
                for size_info in item['sizes']:
                    if isinstance(size_info, dict) and 'url' in size_info:
                        size_name = size_info.get('name', 'unknown')
                        sizes.append(size_name)
                        banner_count += 1
        
        # Count occurrences of each size
        size_counts = Counter(sizes)
        
        print("📐 Available Banner Sizes")
        print("=" * 50)
        print(f"Total banners: {banner_count}")
        print(f"Unique sizes: {len(size_counts)}")
        print()
        
        print("Size distribution:")
        for size, count in sorted(size_counts.items()):
            percentage = (count / banner_count) * 100
            print(f"  {size:<15} : {count:>3} banners ({percentage:5.1f}%)")
        
        print()
        print("💡 Usage Examples:")
        print("  # Get only 300x250 banners:")
        print("  python html_banner_scraper.py --sizes 300x250 --screenshot")
        print()
        print("  # Get multiple specific sizes:")
        print("  python html_banner_scraper.py --sizes 300x250 728x90 160x600 --screenshot")
        print()
        print("  # Get only square banners:")
        print("  python html_banner_scraper.py --sizes 250x250 300x300 --screenshot")
        
    except FileNotFoundError:
        print(f"❌ Error: File '{json_file}' not found")
        print("Make sure you're running this from the correct directory")
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON in '{json_file}'")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main entry point."""
    json_file = sys.argv[1] if len(sys.argv) > 1 else '../frontend/public/htmldesigns.json'
    list_banner_sizes(json_file)


if __name__ == '__main__':
    main()
