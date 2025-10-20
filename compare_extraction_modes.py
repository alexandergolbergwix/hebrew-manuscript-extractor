#!/usr/bin/env python3
"""
Comparison Script for Extraction Modes

Runs extraction in 3 modes on first 100 manuscripts:
1. Normal (regex extraction + AI classification)
2. Kima (regex with Kima gazetteer for locations)
3. AI-Only (AI extracts everything)

Outputs comparison CSV showing differences in dates, locations, persons.
"""

import subprocess
import pandas as pd
import os
import sys
from pathlib import Path


def run_extraction(mode: str, limit: int = 100) -> str:
    """
    Run extraction pipeline in specified mode
    
    Args:
        mode: 'normal', 'kima', or 'ai'
        limit: Number of manuscripts to process
        
    Returns:
        Path to output CSV file
    """
    output_dir = f"output_{mode}"
    
    # Build command
    cmd = [
        "python3", "main.py",
        "--input", "data/input/17th_century_samples.xlsx",
        "--output", output_dir,
        "--limit", str(limit)
    ]
    
    # Add mode-specific flags
    if mode == "normal":
        # Normal mode: regex extraction with legacy gazetteer + AI classification
        cmd.extend([
            "--gazetteer", "data/input/nli_geo_subfield_z_counts_gt5.csv"
        ])
    elif mode == "kima":
        # Kima mode: Kima gazetteer + Hebrew patterns + AI fallback
        cmd.append("--use-kima")
    elif mode == "ai":
        # AI-only mode: Grok extracts everything
        cmd.append("--ai-only")
    
    print(f"\n{'='*80}")
    print(f"Running extraction in {mode.upper()} mode...")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*80}\n")
    
    # Run extraction
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        
        # Return path to entities CSV
        return os.path.join(output_dir, "manuscript_extraction_entities.csv")
        
    except subprocess.CalledProcessError as e:
        print(f"ERROR running {mode} mode:")
        print(e.stderr)
        raise


def load_entities(csv_path: str, mode: str) -> pd.DataFrame:
    """
    Load entities CSV and rename columns with mode prefix
    
    Args:
        csv_path: Path to CSV file
        mode: Mode name for column prefix
        
    Returns:
        DataFrame with renamed columns
    """
    df = pd.read_csv(csv_path)
    
    # Keep only key columns
    columns_to_keep = ['manuscript_id', 'dates', 'locations', 'persons']
    df = df[columns_to_keep]
    
    # Rename entity columns with mode prefix
    df = df.rename(columns={
        'dates': f'dates_{mode}',
        'locations': f'locations_{mode}',
        'persons': f'persons_{mode}'
    })
    
    return df


def count_entities(entity_str: str) -> int:
    """Count number of entities in comma-separated string"""
    if pd.isna(entity_str) or entity_str == '':
        return 0
    # Count by splitting on ', ' and filtering empty strings
    return len([x for x in str(entity_str).split(', ') if x.strip()])


def create_comparison_csv(normal_df, kima_df, ai_df, output_path: str):
    """
    Create comparison CSV with all three modes side-by-side
    
    Args:
        normal_df: DataFrame from normal mode
        kima_df: DataFrame from kima mode
        ai_df: DataFrame from AI-only mode
        output_path: Output CSV path
    """
    # Merge all three on manuscript_id
    comparison = normal_df.merge(
        kima_df, on='manuscript_id', how='outer'
    ).merge(
        ai_df, on='manuscript_id', how='outer'
    )
    
    # Add count columns for easier comparison
    for mode in ['normal', 'kima', 'ai']:
        for entity_type in ['dates', 'locations', 'persons']:
            col = f'{entity_type}_{mode}'
            comparison[f'{col}_count'] = comparison[col].apply(count_entities)
    
    # Reorder columns for better readability
    ordered_cols = ['manuscript_id']
    
    # Add entity columns in order: dates, locations, persons
    # For each entity type, show all modes together
    for entity_type in ['dates', 'locations', 'persons']:
        for mode in ['normal', 'kima', 'ai']:
            ordered_cols.append(f'{entity_type}_{mode}')
            ordered_cols.append(f'{entity_type}_{mode}_count')
    
    comparison = comparison[ordered_cols]
    
    # Save to CSV
    comparison.to_csv(output_path, index=False)
    print(f"\n✓ Comparison CSV saved to: {output_path}")
    
    return comparison


def print_summary(comparison_df):
    """Print summary statistics"""
    print("\n" + "="*80)
    print("EXTRACTION MODE COMPARISON SUMMARY")
    print("="*80)
    
    total_manuscripts = len(comparison_df)
    print(f"\nTotal manuscripts: {total_manuscripts}")
    
    for entity_type in ['dates', 'locations', 'persons']:
        print(f"\n{entity_type.upper()}:")
        for mode in ['normal', 'kima', 'ai']:
            col = f'{entity_type}_{mode}_count'
            total = comparison_df[col].sum()
            avg = comparison_df[col].mean()
            max_val = comparison_df[col].max()
            print(f"  {mode:10s}: {int(total):4d} total, {avg:5.2f} avg, {int(max_val):3d} max")
    
    # Differences analysis
    print("\n" + "="*80)
    print("LOCATION EXTRACTION DIFFERENCES (Normal vs Kima):")
    print("="*80)
    
    # Compare location counts
    comparison_df['location_diff'] = (
        comparison_df['locations_kima_count'] - 
        comparison_df['locations_normal_count']
    )
    
    more_in_kima = (comparison_df['location_diff'] > 0).sum()
    fewer_in_kima = (comparison_df['location_diff'] < 0).sum()
    same = (comparison_df['location_diff'] == 0).sum()
    
    print(f"\nManuscripts with MORE locations in Kima:  {more_in_kima}")
    print(f"Manuscripts with FEWER locations in Kima: {fewer_in_kima}")
    print(f"Manuscripts with SAME locations:          {same}")
    
    if more_in_kima > 0:
        print("\nTop 5 manuscripts with most additional locations in Kima:")
        top_diff = comparison_df.nlargest(5, 'location_diff')[
            ['manuscript_id', 'locations_normal_count', 'locations_kima_count', 'location_diff']
        ]
        print(top_diff.to_string(index=False))


def main():
    """Main execution"""
    print("="*80)
    print("EXTRACTION MODE COMPARISON TOOL")
    print("="*80)
    print("\nThis will run extraction in 3 modes on first 100 manuscripts:")
    print("  1. Normal  - Legacy gazetteer (21k places) + Regex + AI classification")
    print("  2. Kima    - Kima gazetteer (48k places) + Hebrew patterns + AI fallback")
    print("  3. AI-Only - Grok API extracts all entities (no regex)")
    print("\nThis will take 5-10 minutes (AI modes require API calls)...")
    
    # Check if venv is activated
    if not sys.prefix != sys.base_prefix:
        print("\n⚠️  WARNING: Virtual environment may not be activated!")
        print("Run: source venv/bin/activate")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    limit = 100
    modes = ['normal', 'kima', 'ai']
    entity_files = {}
    
    # Run each mode
    for mode in modes:
        try:
            csv_path = run_extraction(mode, limit)
            entity_files[mode] = csv_path
            print(f"✓ {mode.upper()} mode completed: {csv_path}")
        except Exception as e:
            print(f"✗ {mode.upper()} mode FAILED: {e}")
            return
    
    # Load results
    print("\n" + "="*80)
    print("Loading results...")
    print("="*80)
    
    normal_df = load_entities(entity_files['normal'], 'normal')
    kima_df = load_entities(entity_files['kima'], 'kima')
    ai_df = load_entities(entity_files['ai'], 'ai')
    
    print(f"✓ Loaded {len(normal_df)} manuscripts from normal mode")
    print(f"✓ Loaded {len(kima_df)} manuscripts from kima mode")
    print(f"✓ Loaded {len(ai_df)} manuscripts from ai mode")
    
    # Create comparison
    output_path = "extraction_mode_comparison.csv"
    comparison_df = create_comparison_csv(normal_df, kima_df, ai_df, output_path)
    
    # Print summary
    print_summary(comparison_df)
    
    print("\n" + "="*80)
    print("✓ COMPARISON COMPLETE!")
    print("="*80)
    print(f"\nOutput file: {output_path}")
    print(f"Rows: {len(comparison_df)}")
    print(f"\nColumns:")
    print("  - manuscript_id")
    print("  - dates_[mode], dates_[mode]_count")
    print("  - locations_[mode], locations_[mode]_count") 
    print("  - persons_[mode], persons_[mode]_count")
    print("\nwhere [mode] = normal, kima, ai")
    print("\nOpen in Excel/LibreOffice to analyze differences!")


if __name__ == "__main__":
    main()

