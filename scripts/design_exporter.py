#!/usr/bin/env python3
"""
HTML Banner Design Exporter

This module provides functionality to convert scraped HTML banner data into various formats,
starting with the Design object format used by the frontend application.

The exporter handles:
- Global vs per-project asset resolution
- URL path conversion for different asset storage strategies
- Design data structure mapping from scraped data to target formats
- Multiple export formats (Design object, JSON, etc.)

Author: HTML Banner Scraper System
"""

import json
import sys
import os
import argparse
import shutil
import math
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urlparse
import hashlib
import uuid
from datetime import datetime, timezone
import logging

class DesignExporter:
    """
    Exports scraped banner data to various formats including the frontend Design object format.
    
    The exporter works with the directory structure created by the HTML Banner Scraper:
    /output-dir/banner-id/size/
    ├── metadata.json
    ├── design_data.json
    ├── assets.json
    ├── index.html
    ├── screenshot.png
    └── assets/
        ├── asset1.jpg
        ├── asset2.css
        └── ...
    """
    
    def __init__(self, global_assets: bool = False):
        """
        Initialize the exporter.
        
        Args:
            global_assets: Whether assets are stored globally or per-project
        """
        self.global_assets = global_assets
        self.logger = self._setup_logging()
        
    def _setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        return logging.getLogger(__name__)
    
    def export_banner(self, 
                     banner_dir: Path, 
                     output_dir: Path, 
                     size: Optional[str] = None,
                     options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Export a scraped banner to Design object format.
        
        This method works with the scraper's directory structure:
        /banner_dir/size/ (if size is provided)
        or discovers all sizes in /banner_dir/ (if size is None)
        
        Args:
            banner_dir: Directory containing banner data (e.g., ../output/SE014)
            output_dir: Directory to save exported design
            size: Specific size to export (e.g., "300x600"), or None to auto-detect
            options: Export-specific options
            
        Returns:
            Dictionary containing the exported Design object(s)
        """
        self.logger.info(f"🎨 Exporting banner from {banner_dir}")
        
        if not banner_dir.exists():
            raise FileNotFoundError(f"Banner directory not found: {banner_dir}")
        
        # Discover available sizes if not specified
        if size is None:
            available_sizes = self._discover_banner_sizes(banner_dir)
            if not available_sizes:
                raise FileNotFoundError(f"No valid banner sizes found in {banner_dir}")
            
            if len(available_sizes) == 1:
                size = available_sizes[0]
                self.logger.info(f"📐 Auto-detected banner size: {size}")
            else:
                self.logger.info(f"📐 Found multiple sizes: {', '.join(available_sizes)}")
                size = available_sizes[0]  # Use first size as default
                self.logger.info(f"📐 Using default size: {size}")
        
        # Export the specific size
        scraped_dir = banner_dir / size
        return self.export_to_design_object(scraped_dir, output_dir, options)
    
    def export_all_sizes(self,
                        banner_dir: Path,
                        output_dir: Path,
                        options: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Export all available sizes of a scraped banner.
        
        Args:
            banner_dir: Directory containing banner data (e.g., ../output/SE014)
            output_dir: Base directory to save exported designs
            options: Export-specific options
            
        Returns:
            Dictionary mapping size -> Design object
        """
        self.logger.info(f"🎨 Exporting all sizes from {banner_dir}")
        
        available_sizes = self._discover_banner_sizes(banner_dir)
        if not available_sizes:
            raise FileNotFoundError(f"No valid banner sizes found in {banner_dir}")
        
        self.logger.info(f"📐 Found {len(available_sizes)} sizes: {', '.join(available_sizes)}")
        
        exported_designs = {}
        for size in available_sizes:
            try:
                size_output_dir = output_dir / size
                scraped_dir = banner_dir / size
                design_object = self.export_to_design_object(scraped_dir, size_output_dir, options)
                exported_designs[size] = design_object
                self.logger.info(f"✅ Exported {size}")
            except Exception as e:
                self.logger.error(f"❌ Failed to export {size}: {e}")
                continue
        
        return exported_designs
    
    def _discover_banner_sizes(self, banner_dir: Path) -> List[str]:
        """
        Discover available banner sizes in a banner directory.
        
        Args:
            banner_dir: Directory containing banner data
            
        Returns:
            List of available sizes (e.g., ["300x600", "728x90"])
        """
        sizes = []
        
        if not banner_dir.is_dir():
            return sizes
        
        for item in banner_dir.iterdir():
            if item.is_dir() and self._is_valid_size_directory(item):
                sizes.append(item.name)
        
        # Sort sizes for consistent ordering
        sizes.sort()
        return sizes
    
    def _is_valid_size_directory(self, size_dir: Path) -> bool:
        """
        Check if a directory is a valid banner size directory.
        
        Args:
            size_dir: Directory to check
            
        Returns:
            True if it's a valid size directory
        """
        # Check if directory name looks like a size (contains 'x' and digits)
        if 'x' not in size_dir.name.lower():
            return False
        
        # Check if it contains required files
        required_files = ['metadata.json']
        for required_file in required_files:
            if not (size_dir / required_file).exists():
                return False
        
        return True
    
    def export_to_design_object(self, 
                               scraped_dir: Path, 
                               output_dir: Path, 
                               options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Export scraped banner data to frontend Design object format.
        
        Args:
            scraped_dir: Directory containing scraped banner data
            output_dir: Directory to save exported design
            options: Export-specific options
            
        Returns:
            Dictionary containing the exported Design object
        """
        self.logger.info(f"🎨 Exporting banner data from {scraped_dir} to Design object format")
        
        if not scraped_dir.exists():
            raise FileNotFoundError(f"Scraped directory not found: {scraped_dir}")
        
        # Load scraped data
        metadata = self._load_metadata(scraped_dir)
        design_data = self._load_design_data(scraped_dir)
        assets_mapping = self._load_assets_mapping(scraped_dir)
        
        # Convert to Design object format
        design_object = self._convert_to_design_object(
            metadata, design_data, assets_mapping, scraped_dir, options or {}
        )
        
        # Save the Design object
        output_dir.mkdir(parents=True, exist_ok=True)
        design_file = output_dir / 'design.json'
        
        # Copy assets to output directory
        if not self.global_assets:
            self._copy_assets(scraped_dir, output_dir, assets_mapping)
        
        with open(design_file, 'w', encoding='utf-8') as f:
            json.dump(design_object, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"✅ Design object exported to {design_file}")
        return design_object
    
    def _copy_assets(self, scraped_dir: Path, output_dir: Path, assets_mapping: Dict[str, Any]) -> None:
        """
        Copy only the assets that are actually referenced by layers.
        
        Args:
            scraped_dir: Source directory containing assets
            output_dir: Destination directory
            assets_mapping: Asset URL mappings
        """
        self.logger.info(f"📁 Copying referenced assets from {scraped_dir}")
        
        # Determine asset destination based on global_assets setting
        if self.global_assets:
            # Use global assets directory
            assets_output_dir = output_dir.parent / 'global_assets'
            self.logger.info(f"Using global assets directory: {assets_output_dir}")
        else:
            # Use per-project assets directory
            assets_output_dir = output_dir / 'assets'
            self.logger.info(f"Using per-project assets directory: {assets_output_dir}")
        
        # Create assets directory if it doesn't exist
        assets_output_dir.mkdir(parents=True, exist_ok=True)
        
        # First, collect all asset references from the design data
        referenced_assets = self._collect_referenced_assets(scraped_dir)
        
        if not referenced_assets:
            self.logger.info("No assets referenced by layers, skipping asset copying")
            return
        
        self.logger.info(f"Found {len(referenced_assets)} assets referenced by layers")
        
        # Source assets directory
        scraped_assets_dir = scraped_dir / 'assets'
        
        if not scraped_assets_dir.exists():
            # Try to find assets in the parent global_assets directory
            potential_global_assets = scraped_dir.parent.parent / 'global_assets'
            if potential_global_assets.exists():
                self.logger.info(f"Found global assets at {potential_global_assets}")
                scraped_assets_dir = potential_global_assets
            else:
                self.logger.warning(f"No assets directory found in {scraped_dir}")
                return
        
        # Copy only the referenced assets
        copied_count = 0
        
        for asset_reference in referenced_assets:
            try:
                # Extract filename from the asset reference
                if '../global_assets/' in asset_reference:
                    filename = asset_reference.split('/')[-1]
                elif 'assets/' in asset_reference:
                    filename = asset_reference.split('/')[-1]
                else:
                    filename = asset_reference.split('/')[-1] if '/' in asset_reference else asset_reference
                
                # Find the source file
                source_file = scraped_assets_dir / filename
                
                if not source_file.exists():
                    self.logger.warning(f"Referenced asset file not found: {filename}")
                    continue
                
                # Copy to destination
                dest_file = assets_output_dir / filename
                if not dest_file.exists():  # Don't overwrite existing files
                    shutil.copy2(source_file, dest_file)
                    copied_count += 1
                    self.logger.debug(f"✅ Copied referenced asset: {filename}")
                
            except Exception as e:
                self.logger.error(f"Failed to copy referenced asset {asset_reference}: {e}")
                continue
        
        # Copy screenshot if it exists
        screenshot_file = scraped_dir / 'screenshot.png'
        if screenshot_file.exists():
            dest_screenshot = output_dir / 'screenshot.png'
            try:
                shutil.copy2(screenshot_file, dest_screenshot)
                copied_count += 1
                self.logger.debug("✅ Copied screenshot.png")
            except Exception as e:
                self.logger.warning(f"Failed to copy screenshot: {e}")
        
        self.logger.info(f"📁 Copied {copied_count} referenced assets to {assets_output_dir}")
        
        # List what was copied for debugging
        if assets_output_dir.exists():
            copied_files = [f.name for f in assets_output_dir.iterdir() if f.is_file()]
            self.logger.debug(f"Copied assets: {', '.join(copied_files[:10])}")
            if len(copied_files) > 10:
                self.logger.debug(f"... and {len(copied_files) - 10} more files")
    
    def _collect_referenced_assets(self, scraped_dir: Path) -> set:
        """
        Collect all asset references from the design layers.
        
        Args:
            scraped_dir: Source directory containing design data
            
        Returns:
            Set of asset paths referenced by layers
        """
        referenced_assets = set()
        
        try:
            # Load design data to analyze layer assets
            design_data = self._load_design_data(scraped_dir)
            layers = design_data.get('layers', [])
            
            for layer in layers:
                layer_type = layer.get('type', '')
                content = layer.get('content', {})
                
                # Check for image assets
                if layer_type == 'image' and content.get('src'):
                    src_path = content['src']
                    referenced_assets.add(src_path)
                    self.logger.debug(f"Found image asset reference: {src_path}")
                
                # Check for background images in styles
                styles = layer.get('styles', {})
                background = styles.get('background', '')
                if background and ('url(' in background or '.jpg' in background or '.png' in background or '.gif' in background):
                    # Extract URL from background property
                    import re
                    url_match = re.search(r'url\(["\']?([^"\']+)["\']?\)', background)
                    if url_match:
                        bg_url = url_match.group(1)
                        referenced_assets.add(bg_url)
                        self.logger.debug(f"Found background asset reference: {bg_url}")
            
            self.logger.info(f"Collected {len(referenced_assets)} asset references from layers")
            
        except Exception as e:
            self.logger.error(f"Failed to collect asset references: {e}")
        
        return referenced_assets

    def _load_metadata(self, scraped_dir: Path) -> Dict[str, Any]:
        """Load metadata from scraped banner directory."""
        metadata_file = scraped_dir / 'metadata.json'
        if not metadata_file.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_file}")
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _load_design_data(self, scraped_dir: Path) -> Dict[str, Any]:
        """Load design data from scraped banner directory."""
        design_file = scraped_dir / 'design_data.json'
        if design_file.exists():
            with open(design_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _load_assets_mapping(self, scraped_dir: Path) -> Dict[str, Any]:
        """Load assets mapping from scraped banner directory."""
        assets_file = scraped_dir / 'assets.json'
        if assets_file.exists():
            with open(assets_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _convert_to_design_object(self, 
                                  metadata: Dict[str, Any], 
                                  design_data: Dict[str, Any],
                                  assets_mapping: Dict[str, Any],
                                  scraped_dir: Path,
                                  options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert scraped data to frontend Design object format.
        
        Args:
            metadata: Banner metadata
            design_data: Extracted design data
            assets_mapping: Asset URL mappings
            scraped_dir: Source directory for the scraped data
            options: Export options
            
        Returns:
            Design object compatible with frontend
        """
        self.logger.info("🔄 Converting scraped data to Design object format")
        
        # Generate unique design ID
        design_id = options.get('design_id', f"scraped_{uuid.uuid4().hex[:8]}")
        
        # Extract banner dimensions
        banner_width = metadata.get('canvas', {}).get('width', 800)
        banner_height = metadata.get('canvas', {}).get('height', 600)
        
        # Create base Design object structure
        design_object = {
            "id": design_id,
            "name": metadata.get('banner_id', 'Scraped Banner'),
            "title": metadata.get('banner_id', 'Scraped Banner'),
            "description": f"Scraped from {metadata.get('source_url', 'unknown source')}",
            "width": banner_width,
            "height": banner_height,
            "userId": options.get('user_id', 'scraper'),
            "projectId": options.get('project_id'),
            "isPublic": options.get('is_public', False),
            "createdAt": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "updatedAt": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "syncStatus": "synced",
            "isTemporary": False,
            "data": self._create_design_data(metadata, design_data, options),
            "layers": self._convert_layers(design_data, assets_mapping, scraped_dir, options)
        }
        
        # Add thumbnail if available
        screenshot_file = scraped_dir / 'screenshot.png'
        if screenshot_file.exists():
            design_object["thumbnail"] = self._resolve_asset_path("screenshot.png", scraped_dir)
        
        return design_object
    
    def _create_design_data(self, 
                           metadata: Dict[str, Any], 
                           design_data: Dict[str, Any],
                           options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create the DesignData object with canvas settings and configurations.
        
        Args:
            metadata: Banner metadata
            design_data: Extracted design data
            options: Export options
            
        Returns:
            DesignData object
        """
        canvas_config = metadata.get('canvas', {})
        
        design_data_obj = {
            "backgroundColor": canvas_config.get('background_color', '#ffffff'),
            "background": {
                "type": "solid",
                "color": canvas_config.get('background_color', '#ffffff')
            },
            "animationSettings": design_data.get('animations', {}),
            "customProperties": {
                "sourceUrl": metadata.get('source_url'),
                "scrapedAt": metadata.get('scraped_at'),
                "bannerType": metadata.get('banner_type', 'html5'),
                "originalSize": metadata.get('size', 'unknown')
            },
            "globalStyles": design_data.get('styles', {}),
            "gridSettings": {
                "gridSize": 20,
                "showGrid": False,
                "snapToGrid": False,
                "snapToObjects": False,
                "snapTolerance": 5
            },
            "viewportSettings": {
                "zoom": 1,
                "panX": 0,
                "panY": 0
            }
        }
        
        return design_data_obj
    
    def _convert_layers(self, 
                       design_data: Dict[str, Any], 
                       assets_mapping: Dict[str, Any],
                       scraped_dir: Path,
                       options: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert scraped layer data to frontend Layer objects.
        
        Args:
            design_data: Extracted design data containing layers
            assets_mapping: Asset URL to local path mappings
            scraped_dir: Source directory for resolving asset paths
            options: Export options
            
        Returns:
            List of Layer objects
        """
        layers = []
        
        # Get the main layers array from the scraped data
        scraped_layers = design_data.get('layers', [])
        
        self.logger.info(f"🔄 Converting {len(scraped_layers)} layers from scraped data")
        
        for layer_index, layer_data in enumerate(scraped_layers):
            try:
                layer = self._convert_scraped_layer(layer_data, assets_mapping, scraped_dir, layer_index)
                if layer:
                    layers.append(layer)
            except Exception as e:
                self.logger.warning(f"Failed to convert layer {layer_data.get('id', 'unknown')}: {e}")
                continue
        
        # Sort layers by zIndex for proper ordering
        layers.sort(key=lambda x: x.get('transform', {}).get('zIndex', 0))
        
        self.logger.info(f"✅ Successfully converted {len(layers)} layers")
        return layers
    
    def _convert_scraped_layer(self, 
                              layer_data: Dict[str, Any], 
                              assets_mapping: Dict[str, Any],
                              scraped_dir: Path,
                              layer_index: int) -> Dict[str, Any]:
        """
        Convert a scraped layer to frontend Layer object.
        
        Args:
            layer_data: Raw layer data from scraping
            assets_mapping: Asset URL to local path mappings
            scraped_dir: Source directory for resolving asset paths
            layer_index: Layer index for ordering
            
        Returns:
            Layer object
        """
        position = layer_data.get('position', {})
        styles = layer_data.get('styles', {})
        content = layer_data.get('content', {})
        
        # Determine layer type from scraped data
        layer_type = layer_data.get('type', 'text')
        
        # Generate transform with proper zIndex handling
        transform = {
            'x': float(position.get('x', 0)),
            'y': float(position.get('y', 0)),
            'width': float(position.get('width', 100)),
            'height': float(position.get('height', 100)),
            'rotation': self._extract_rotation_from_transform(styles.get('transform')),
            'scaleX': 1.0,
            'scaleY': 1.0,
            'opacity': float(styles.get('opacity', 1))
        }
        
        layer = {
            'id': layer_data.get('id', f'layer_{layer_index}'),
            'type': layer_type,
            'name': layer_data.get('semanticRole', f'{layer_type.title()} {layer_index + 1}'),
            'visible': True,
            'locked': False,
            'zIndex': position.get('zIndex', layer_index),
            'syncStatus': 'synced',
            'isTemporary': False,
            'transform': transform,
            'properties': self._extract_layer_properties_from_scraped(layer_data, assets_mapping, scraped_dir)
        }
        
        return layer
    
    def _extract_rotation_from_transform(self, transform_str: Optional[str]) -> float:
        """
        Extract rotation angle from CSS transform matrix.
        
        Args:
            transform_str: CSS transform string (e.g., "matrix(-0.865838, 0.500325, ...)")
            
        Returns:
            Rotation angle in degrees
        """
        if not transform_str or 'matrix' not in transform_str:
            return 0.0
        
        try:
            # Extract matrix values from transform string
            import re
            match = re.search(r'matrix\(([^)]+)\)', transform_str)
            if match:
                values = [float(x.strip()) for x in match.group(1).split(',')]
                if len(values) >= 2:
                    # Calculate rotation from matrix a and b values
                    a, b = values[0], values[1]
                    rotation_rad = math.atan2(b, a)
                    rotation_deg = math.degrees(rotation_rad)
                    return rotation_deg
        except (ValueError, IndexError):
            pass
        
        return 0.0
    
    def _extract_layer_properties_from_scraped(self, 
                                              layer_data: Dict[str, Any], 
                                              assets_mapping: Dict[str, Any],
                                              scraped_dir: Path) -> Dict[str, Any]:
        """
        Extract layer-specific properties from scraped layer data.
        
        Args:
            layer_data: Raw layer data from scraping
            assets_mapping: Asset URL to local path mappings
            scraped_dir: Source directory for resolving asset paths
            
        Returns:
            Layer properties dict
        """
        layer_type = layer_data.get('type', 'text')
        content = layer_data.get('content', {})
        styles = layer_data.get('styles', {})
        
        properties = {}
        
        if layer_type == 'image':
            # Handle image layer properties
            src_path = content.get('src', '')
            
            # Resolve the asset path for export
            resolved_src = self._resolve_image_asset_for_export(src_path, assets_mapping, scraped_dir)
            
            properties.update({
                'src': resolved_src,
                'alt': content.get('alt', ''),
                'objectFit': 'contain',  # Default fit for scraped images
                'filters': {},
                'border': {},
                'shadow': {}
            })
        
        elif layer_type == 'text':
            # Handle text layer properties
            properties.update({
                'text': content.get('text', ''),
                'fontFamily': self._clean_font_family(styles.get('fontFamily', 'Arial')),
                'fontSize': self._parse_font_size(styles.get('fontSize', '16px')),
                'fontWeight': styles.get('fontWeight', 'normal'),
                'fontStyle': styles.get('fontStyle', 'normal'),
                'color': styles.get('color', '#000000'),
                'textAlign': styles.get('textAlign', 'left'),
                'textDecoration': 'none',
                'lineHeight': 1.2,
                'letterSpacing': 0,
                'background': {},
                'border': {},
                'shadow': {}
            })
        
        # Add animation information if present
        if layer_data.get('animationInfo'):
            properties['animations'] = [layer_data['animationInfo']]
        else:
            properties['animations'] = []
        
        return properties
    
    def _resolve_image_asset_for_export(self, 
                                       src_path: str, 
                                       assets_mapping: Dict[str, Any],
                                       scraped_dir: Path) -> str:
        """
        Resolve image asset path for export, ensuring the asset is copied.
        
        Args:
            src_path: Original source path from scraped data
            assets_mapping: Asset URL to local path mappings
            scraped_dir: Source directory for resolving asset paths
            
        Returns:
            Resolved asset path for the exported design
        """
        if not src_path:
            return ''
        
        # If it's already a global asset path, extract the filename
        if '../global_assets/' in src_path:
            filename = src_path.split('/')[-1]
            
            # For global assets mode, keep the global path
            if self.global_assets:
                return src_path
            else:
                # For per-project mode, change to local assets path
                return f"assets/{filename}"
        
        # For other asset types, try to find in mapping
        for asset_name, asset_path in assets_mapping.items():
            if src_path in asset_path or asset_name in src_path:
                filename = asset_path.split('/')[-1] if '/' in asset_path else asset_name
                
                if self.global_assets:
                    return asset_path  # Keep global path
                else:
                    return f"assets/{filename}"  # Use local assets path
        
        # Fallback: extract filename from src_path
        filename = src_path.split('/')[-1] if '/' in src_path else src_path
        
        if self.global_assets:
            return f"../global_assets/{filename}"
        else:
            return f"assets/{filename}"
    
    def _clean_font_family(self, font_family: str) -> str:
        """
        Clean font family string by removing quotes and extra formatting.
        
        Args:
            font_family: Font family string from styles
            
        Returns:
            Cleaned font family string
        """
        if not font_family:
            return 'Arial'
        
        # Remove quotes and extra spaces
        cleaned = font_family.strip().strip('"').strip("'")
        return cleaned if cleaned else 'Arial'
    
    def _parse_font_size(self, font_size: str) -> float:
        """
        Parse font size from CSS string to numeric value.
        
        Args:
            font_size: Font size string (e.g., "16px", "1.2em")
            
        Returns:
            Font size as float (in pixels)
        """
        if not font_size:
            return 16.0
        
        try:
            # Extract numeric part
            import re
            match = re.search(r'([\d.]+)', str(font_size))
            if match:
                return float(match.group(1))
        except (ValueError, AttributeError):
            pass
        
        return 16.0

    def _convert_scraped_text_to_layer(self, 
                                      text_data: Dict[str, Any], 
                                      layer_index: int) -> Dict[str, Any]:
        """
        Convert a scraped text element to frontend Text Layer.
        
        Args:
            text_data: Raw text data from scraping
            layer_index: Layer index for ordering
            
        Returns:
            Text Layer object
        """
        position = text_data.get('position', {})
        styles = text_data.get('styles', {})
        content = text_data.get('content', {})
        
        layer = {
            'id': text_data.get('id', f'text_{layer_index}'),
            'type': 'text',
            'name': f'Text {layer_index + 1}',
            'visible': text_data.get('visible', True),
            'locked': text_data.get('locked', False),
            'zIndex': position.get('zIndex', layer_index),
            'syncStatus': 'synced',
            'isTemporary': False,
            'transform': {
                'x': position.get('x', 0),
                'y': position.get('y', 0),
                'width': position.get('width', 100),
                'height': position.get('height', 50),
                'rotation': position.get('rotation', 0),
                'scaleX': position.get('scaleX', 1),
                'scaleY': position.get('scaleY', 1),
                'opacity': position.get('opacity', 1)
            },
            'properties': {
                'text': content.get('text', ''),
                'fontFamily': styles.get('fontFamily', 'Arial'),
                'fontSize': styles.get('fontSize', 16),
                'fontWeight': styles.get('fontWeight', 'normal'),
                'fontStyle': styles.get('fontStyle', 'normal'),
                'color': styles.get('color', '#000000'),
                'textAlign': styles.get('textAlign', 'left'),
                'textDecoration': styles.get('textDecoration', 'none'),
                'lineHeight': styles.get('lineHeight', 1.2),
                'letterSpacing': styles.get('letterSpacing', 0),
                'background': styles.get('background', {}),
                'border': text_data.get('border', {}),
                'shadow': text_data.get('shadow', {})
            }
        }
        
        return layer
    
    def _determine_layer_type(self, layer_data: Dict[str, Any]) -> str:
        """
        Determine the layer type based on scraped data.
        
        Args:
            layer_data: Raw layer data from scraping
            
        Returns:
            Layer type string
        """
        content = layer_data.get('content', {})
        
        # Check for image content
        if content.get('src'):
            return 'image'
        
        # Check for text content
        if content.get('text'):
            return 'text'
        
        # Check for semantic role hints
        semantic_role = layer_data.get('semanticRole', '').lower()
        if 'image' in semantic_role or 'picture' in semantic_role:
            return 'image'
        elif 'text' in semantic_role or 'heading' in semantic_role or 'paragraph' in semantic_role:
            return 'text'
        elif 'button' in semantic_role or 'link' in semantic_role:
            return 'button'
        elif 'shape' in semantic_role or 'rect' in semantic_role or 'circle' in semantic_role:
            return 'shape'
        
        # Default to shape for unknown types
        return 'shape'
    
    def _extract_layer_properties(self, 
                                 layer_data: Dict[str, Any], 
                                 assets_mapping: Dict[str, Any],
                                 scraped_dir: Path) -> Dict[str, Any]:
        """
        Extract layer-specific properties based on type.
        
        Args:
            layer_data: Raw layer data from scraping
            assets_mapping: Asset URL to local path mappings
            scraped_dir: Source directory for resolving asset paths
            
        Returns:
            Layer properties dict
        """
        layer_type = self._determine_layer_type(layer_data)
        content = layer_data.get('content', {})
        styles = layer_data.get('styles', {})
        
        properties = {}
        
        if layer_type == 'image':
            # Resolve image asset path from assets mapping
            local_filename = None
            src_url = content.get('src', '')
            
            # Find local filename from assets mapping
            for asset_file, asset_path in assets_mapping.items():
                if src_url in asset_path or asset_file in src_url:
                    local_filename = asset_file
                    break
            
            if not local_filename:
                # Fallback: extract filename from URL
                local_filename = src_url.split('/')[-1] if src_url else 'placeholder.jpg'
                
            image_src = self._resolve_asset_path(local_filename, scraped_dir)
            properties.update({
                'src': image_src,
                'alt': layer_data.get('alt', ''),
                'objectFit': content.get('objectFit', 'contain')
            })
        
        elif layer_type == 'text':
            properties.update({
                'text': content.get('text', ''),
                'fontFamily': styles.get('fontFamily', 'Arial'),
                'fontSize': styles.get('fontSize', 16),
                'fontWeight': styles.get('fontWeight', 'normal'),
                'fontStyle': styles.get('fontStyle', 'normal'),
                'color': styles.get('color', '#000000'),
                'textAlign': styles.get('textAlign', 'left'),
                'textDecoration': styles.get('textDecoration', 'none'),
                'lineHeight': styles.get('lineHeight', 1.2),
                'letterSpacing': styles.get('letterSpacing', 0)
            })
        
        elif layer_type == 'shape':
            properties.update({
                'fill': styles.get('background', '#ffffff'),
                'stroke': styles.get('borderColor', '#000000'),
                'strokeWidth': styles.get('borderWidth', 0),
                'shapeType': layer_data.get('shapeType', 'rectangle')
            })
        
        # Add common properties
        properties.update({
            'filters': layer_data.get('filters', {}),
            'border': layer_data.get('border', {}),
            'shadow': layer_data.get('shadow', {}),
            'background': styles.get('background', {}),
            'animations': layer_data.get('animations', [])
        })
        
        return properties
        
        if layer_type == 'text':
            return self._convert_text_properties(properties)
        elif layer_type == 'image':
            return self._convert_image_properties(properties, assets_mapping, scraped_dir)
        elif layer_type == 'shape':
            return self._convert_shape_properties(properties)
        elif layer_type == 'svg':
            return self._convert_svg_properties(properties, assets_mapping, scraped_dir)
        else:
            # Return base properties for unsupported types
            return properties
    
    def _convert_text_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Convert text layer properties to frontend format."""
        return {
            "text": properties.get('text', 'Text'),
            "fontFamily": properties.get('fontFamily', 'Arial'),
            "fontSize": float(properties.get('fontSize', 16)),
            "fontWeight": properties.get('fontWeight', 'normal'),
            "fontStyle": properties.get('fontStyle', 'normal'),
            "textAlign": properties.get('textAlign', 'left'),
            "color": properties.get('color', '#000000'),
            "lineHeight": float(properties.get('lineHeight', 1.2)),
            "letterSpacing": float(properties.get('letterSpacing', 0)),
            "textDecoration": properties.get('textDecoration', 'none'),
            "autoResize": {
                "enabled": False,
                "mode": "none"
            }
        }
    
    def _convert_image_properties(self, 
                                 properties: Dict[str, Any], 
                                 assets_mapping: Dict[str, Any],
                                 scraped_dir: Path) -> Dict[str, Any]:
        """Convert image layer properties to frontend format."""
        original_src = properties.get('src', '')
        resolved_src = self._resolve_asset_url(original_src, assets_mapping, scraped_dir)
        
        return {
            "src": resolved_src,
            "alt": properties.get('alt', ''),
            "fit": properties.get('fit', 'contain'),
            "filters": properties.get('filters', []),
            "shadow": {
                "enabled": False,
                "offsetX": 0,
                "offsetY": 0,
                "blur": 0,
                "color": "#000000",
                "opacity": 0.3
            }
        }
    
    def _convert_shape_properties(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Convert shape layer properties to frontend format."""
        return {
            "shapeType": properties.get('shapeType', 'rectangle'),
            "fill": {
                "type": "solid",
                "color": properties.get('fill', '#000000'),
                "opacity": 1
            },
            "stroke": properties.get('stroke', 'transparent'),
            "strokeWidth": float(properties.get('strokeWidth', 0)),
            "strokeOpacity": float(properties.get('strokeOpacity', 1)),
            "cornerRadius": float(properties.get('cornerRadius', 0)),
            "sides": int(properties.get('sides', 4)),
            "points": int(properties.get('points', 5)),
            "innerRadius": float(properties.get('innerRadius', 0.5)),
            "x1": float(properties.get('x1', 0)),
            "y1": float(properties.get('y1', 0)),
            "x2": float(properties.get('x2', 100)),
            "y2": float(properties.get('y2', 100))
        }
    
    def _convert_svg_properties(self, 
                               properties: Dict[str, Any], 
                               assets_mapping: Dict[str, Any],
                               scraped_dir: Path) -> Dict[str, Any]:
        """Convert SVG layer properties to frontend format."""
        original_src = properties.get('src', '')
        resolved_src = self._resolve_asset_url(original_src, assets_mapping, scraped_dir)
        
        return {
            "src": resolved_src,
            "svgContent": properties.get('svgContent', ''),
            "preserveAspectRatio": properties.get('preserveAspectRatio', 'xMidYMid meet'),
            "fill": properties.get('fill', ''),
            "stroke": properties.get('stroke', ''),
            "strokeWidth": float(properties.get('strokeWidth', 1))
        }
    
    def _resolve_asset_url(self, 
                          original_url: str, 
                          assets_mapping: Dict[str, Any],
                          scraped_dir: Path) -> str:
        """
        Resolve asset URL to the appropriate path based on storage strategy.
        
        Args:
            original_url: Original asset URL from scraper
            assets_mapping: URL to local path mappings
            scraped_dir: Source directory
            
        Returns:
            Resolved asset path for the exported design
        """
        if not original_url:
            return ''
        
        # Check if we have a mapping for this URL
        if original_url in assets_mapping:
            local_filename = assets_mapping[original_url]
            return self._resolve_asset_path(local_filename, scraped_dir)
        
        # If no mapping found, try to find by filename
        parsed_url = urlparse(original_url)
        filename = Path(parsed_url.path).name
        if filename:
            assets_dir = scraped_dir / 'assets'
            asset_file = assets_dir / filename
            if asset_file.exists():
                return self._resolve_asset_path(filename, scraped_dir)
        
        # Fallback: return original URL
        self.logger.warning(f"Could not resolve asset URL: {original_url}")
        return original_url
    
    def _resolve_asset_path(self, local_filename: str, scraped_dir: Path) -> str:
        """
        Resolve local asset filename to the appropriate path for the export format.
        
        Args:
            local_filename: Local asset filename
            scraped_dir: Source directory
            
        Returns:
            Asset path for the exported design
        """
        if self.global_assets:
            # Global assets: path relative to global assets directory
            return f"../global_assets/{local_filename}"
        else:
            # Per-project assets: path relative to design directory
            return f"assets/{local_filename}"

def main():
    """Command-line interface for the design exporter."""
    parser = argparse.ArgumentParser(
        description='Export scraped HTML banner data to various formats',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Export single banner (auto-detect size)
    python design_exporter.py --banner-dir ../output/SE014 --output-dir ../exported/SE014

    # Export specific size
    python design_exporter.py --banner-dir ../output/SE014 --output-dir ../exported/SE014 --size 300x600

    # Export all sizes
    python design_exporter.py --banner-dir ../output/SE014 --output-dir ../exported/SE014 --all-sizes

    # Export with global assets mode
    python design_exporter.py --banner-dir ../output/SE014 --output-dir ../exported/SE014 --global-assets

    # Export with custom options
    python design_exporter.py --banner-dir ../output/SE014 --output-dir ../exported/SE014 --user-id user123 --project-id proj456

    # Legacy mode: specify exact scraped directory
    python design_exporter.py --scraped-dir ../output/SE014/300x600 --output-dir ../exported/SE014
        """
    )
    
    # Main arguments
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--banner-dir', type=str,
                       help='Directory containing banner data (e.g., ../output/SE014)')
    group.add_argument('--scraped-dir', type=str,
                       help='[LEGACY] Specific scraped directory (e.g., ../output/SE014/300x600)')
    
    parser.add_argument('--output-dir', type=str, required=True,
                       help='Directory to save exported design')
    
    # Size options
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument('--size', type=str,
                           help='Specific size to export (e.g., 300x600)')
    size_group.add_argument('--all-sizes', action='store_true',
                           help='Export all available sizes')
    
    # Format and export options
    parser.add_argument('--format', type=str, default='design',
                       choices=['design', 'json'],
                       help='Export format (default: design)')
    parser.add_argument('--global-assets', action='store_true',
                       help='Use global assets mode (assets stored globally)')
    parser.add_argument('--user-id', type=str, default='scraper',
                       help='User ID for the exported design')
    parser.add_argument('--project-id', type=str,
                       help='Project ID for the exported design')
    parser.add_argument('--design-id', type=str,
                       help='Custom design ID (auto-generated if not provided)')
    parser.add_argument('--is-public', action='store_true',
                       help='Mark the design as public')
    
    args = parser.parse_args()
    
    # Create exporter
    exporter = DesignExporter(global_assets=args.global_assets)
    
    # Export options
    options = {
        'user_id': args.user_id,
        'project_id': args.project_id,
        'design_id': args.design_id,
        'is_public': args.is_public
    }
    
    try:
        if args.format != 'design':
            print(f"❌ Unsupported format: {args.format}")
            sys.exit(1)
        
        output_dir = Path(args.output_dir).resolve()
        
        if args.scraped_dir:
            # Legacy mode: direct scraped directory
            scraped_dir = Path(args.scraped_dir).resolve()
            design_object = exporter.export_to_design_object(scraped_dir, output_dir, options)
            print(f"✅ Design exported successfully to {output_dir}")
            print(f"📊 Design contains {len(design_object.get('layers', []))} layers")
            
        elif args.banner_dir:
            # New mode: banner directory with size auto-detection
            banner_dir = Path(args.banner_dir).resolve()
            
            if args.all_sizes:
                # Export all sizes
                exported_designs = exporter.export_all_sizes(banner_dir, output_dir, options)
                print(f"✅ Exported {len(exported_designs)} sizes to {output_dir}")
                for size, design in exported_designs.items():
                    layer_count = len(design.get('layers', []))
                    print(f"   📐 {size}: {layer_count} layers")
            else:
                # Export single size (specified or auto-detected)
                design_object = exporter.export_banner(banner_dir, output_dir, args.size, options)
                print(f"✅ Design exported successfully to {output_dir}")
                print(f"📊 Design contains {len(design_object.get('layers', []))} layers")
            
    except Exception as e:
        print(f"❌ Export failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
