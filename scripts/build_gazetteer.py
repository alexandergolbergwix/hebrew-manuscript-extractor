#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build Location Gazetteer from NLI Authority XML Files

Extracts location names from <subfield code="z"> tags across all XML files,
counts occurrences, and creates a gazetteer CSV with locations appearing > 5 times
and having length > 3 characters.
"""

import os
import gzip
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import csv
from typing import Set, Dict


def extract_locations_from_xml(xml_path: str) -> Set[str]:
    """
    Extract all location names from <subfield code="z"> in an XML file
    
    Args:
        xml_path: Path to XML or XML.gz file
        
    Returns:
        Set of location names found
    """
    locations = set()
    
    try:
        # Handle gzipped files
        if xml_path.endswith('.gz'):
            with gzip.open(xml_path, 'rt', encoding='utf-8') as f:
                content = f.read()
        else:
            with open(xml_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # Parse XML
        root = ET.fromstring(content)
        
        # Find all <subfield code="z"> tags
        # XML namespace handling
        for subfield in root.findall('.//subfield[@code="z"]'):
            location = subfield.text
            if location:
                location = location.strip()
                # Filter by length > 3
                if len(location) > 3:
                    locations.add(location)
        
        print(f"✓ Processed {xml_path}: {len(locations)} unique locations")
        
    except Exception as e:
        print(f"✗ Error processing {xml_path}: {e}")
    
    return locations


def build_gazetteer_from_directory(
    directory: str,
    output_csv: str,
    min_occurrences: int = 5,
    min_length: int = 3
):
    """
    Build gazetteer from all XML files in directory
    
    Args:
        directory: Path to directory containing NLI Authority XML files
        output_csv: Output CSV file path
        min_occurrences: Minimum count to include in gazetteer (default: 5)
        min_length: Minimum character length (default: 3)
    """
    print("=" * 80)
    print("BUILDING LOCATION GAZETTEER FROM NLI AUTHORITY XML FILES")
    print("=" * 80)
    print()
    
    # Counter for all locations across all files
    location_counter = Counter()
    
    # Find all XML and XML.gz files
    xml_files = []
    for ext in ['*.xml', '*.xml.gz']:
        xml_files.extend(Path(directory).glob(ext))
    
    print(f"Found {len(xml_files)} XML files to process")
    print()
    
    # Process each file
    for xml_file in sorted(xml_files):
        locations = extract_locations_from_xml(str(xml_file))
        location_counter.update(locations)
    
    print()
    print(f"Total unique locations found: {len(location_counter)}")
    print()
    
    # Filter by minimum occurrences and length
    filtered_locations = {
        loc: count 
        for loc, count in location_counter.items()
        if count > min_occurrences and len(loc) > min_length
    }
    
    print(f"After filtering (count > {min_occurrences}, length > {min_length}):")
    print(f"  Locations remaining: {len(filtered_locations)}")
    print()
    
    # Sort by count (descending)
    sorted_locations = sorted(
        filtered_locations.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    # Save to CSV
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['location', 'count'])
        writer.writerows(sorted_locations)
    
    print(f"✓ Gazetteer saved to: {output_csv}")
    print()
    
    # Print statistics
    print("=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Total locations: {len(sorted_locations)}")
    print(f"Most common locations:")
    for location, count in sorted_locations[:20]:
        print(f"  {count:6d}  {location}")
    print()
    
    # Hebrew vs. non-Hebrew
    hebrew_count = sum(1 for loc, _ in sorted_locations if any('\u0590' <= c <= '\u05FF' for c in loc))
    non_hebrew_count = len(sorted_locations) - hebrew_count
    print(f"Hebrew locations: {hebrew_count}")
    print(f"Non-Hebrew locations: {non_hebrew_count}")
    print()


if __name__ == "__main__":
    import sys
    
    # Default paths
    DEFAULT_INPUT_DIR = "data/input/NLI_AUTHORITY_XML"
    DEFAULT_OUTPUT_CSV = "data/input/nli_geo_subfield_z_counts_gt5.csv"
    
    # Get paths from command line or use defaults
    input_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_DIR
    output_csv = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_CSV
    
    # Build gazetteer
    build_gazetteer_from_directory(
        directory=input_dir,
        output_csv=output_csv,
        min_occurrences=5,
        min_length=3
    )
    
    print("✅ GAZETTEER BUILD COMPLETE!")
