#!/usr/bin/env python3
"""
Screenshot verification script to check that the captured banners
have the correct dimensions and are properly cropped.
"""

import os
import sys
from pathlib import Path
from PIL import Image

def verify_screenshots(output_dir="scraped_banners"):
    """Verify that screenshots have correct dimensions."""
    output_path = Path(output_dir)
    
    if not output_path.exists():
        print(f"❌ Output directory not found: {output_path}")
        return
    
    print("🔍 Verifying Banner Screenshots")
    print("=" * 40)
    
    total_checked = 0
    correct_dimensions = 0
    
    for banner_dir in output_path.iterdir():
        if not banner_dir.is_dir():
            continue
            
        banner_id = banner_dir.name
        print(f"\n📁 Banner: {banner_id}")
        
        for size_dir in banner_dir.iterdir():
            if not size_dir.is_dir():
                continue
                
            size_name = size_dir.name
            screenshot_file = size_dir / "screenshot.png"
            
            if not screenshot_file.exists():
                print(f"  ⚠️  {size_name}: No screenshot found")
                continue
            
            try:
                # Parse expected dimensions
                if 'x' in size_name:
                    expected_width, expected_height = map(int, size_name.split('x'))
                else:
                    print(f"  ⚠️  {size_name}: Invalid size format")
                    continue
                
                # Check actual image dimensions
                with Image.open(screenshot_file) as img:
                    actual_width, actual_height = img.size
                    
                total_checked += 1
                
                # Check if dimensions match (allow small tolerance)
                width_match = abs(actual_width - expected_width) <= 5
                height_match = abs(actual_height - expected_height) <= 5
                
                if width_match and height_match:
                    print(f"  ✅ {size_name}: {actual_width}x{actual_height} (Perfect match)")
                    correct_dimensions += 1
                else:
                    print(f"  📏 {size_name}: {actual_width}x{actual_height} (Expected: {expected_width}x{expected_height})")
                    
                # Check file size
                file_size = screenshot_file.stat().st_size / 1024  # KB
                print(f"      File size: {file_size:.1f} KB")
                
            except Exception as e:
                print(f"  ❌ {size_name}: Error reading screenshot - {e}")
    
    print("\n" + "=" * 40)
    print(f"📊 Summary:")
    print(f"   Total checked: {total_checked}")
    print(f"   Correct dimensions: {correct_dimensions}")
    if total_checked > 0:
        accuracy = (correct_dimensions / total_checked) * 100
        print(f"   Accuracy: {accuracy:.1f}%")
        
        if accuracy >= 90:
            print("   🎉 Excellent screenshot quality!")
        elif accuracy >= 70:
            print("   👍 Good screenshot quality!")
        else:
            print("   ⚠️  Screenshot quality needs improvement")

def show_screenshot_info(banner_id, size):
    """Show detailed information about a specific screenshot."""
    screenshot_file = Path(f"scraped_banners/{banner_id}/{size}/screenshot.png")
    
    if not screenshot_file.exists():
        print(f"❌ Screenshot not found: {screenshot_file}")
        return
    
    try:
        with Image.open(screenshot_file) as img:
            print(f"🖼️  Screenshot Info: {banner_id} ({size})")
            print(f"   Dimensions: {img.size[0]}x{img.size[1]}")
            print(f"   Mode: {img.mode}")
            print(f"   Format: {img.format}")
            print(f"   File size: {screenshot_file.stat().st_size / 1024:.1f} KB")
            
            # Show if it matches expected dimensions
            if 'x' in size:
                expected_width, expected_height = map(int, size.split('x'))
                width_match = abs(img.size[0] - expected_width) <= 5
                height_match = abs(img.size[1] - expected_height) <= 5
                
                if width_match and height_match:
                    print("   ✅ Dimensions match expected size")
                else:
                    print(f"   📏 Expected: {expected_width}x{expected_height}")
                    
    except Exception as e:
        print(f"❌ Error reading screenshot: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--info" and len(sys.argv) >= 4:
            # Show info for specific banner
            show_screenshot_info(sys.argv[2], sys.argv[3])
        else:
            # Use custom output directory
            verify_screenshots(sys.argv[1])
    else:
        # Use default output directory
        verify_screenshots()
        
        print("\n💡 Tips:")
        print("   • Use --info <banner_id> <size> for detailed info")
        print("   • Example: python verify_screenshots.py --info tt023 160x600")
