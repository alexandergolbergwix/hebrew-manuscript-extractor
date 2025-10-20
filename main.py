#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hebrew Manuscript Entity Extraction System - Main Entry Point
CLI interface for running extraction with various modes
"""

import argparse
import os
import sys
from pathlib import Path

from src.models.entities import Config
from src.pipeline import run_extraction_pipeline


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Hebrew Manuscript Entity Extraction System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard regex-based extraction with AI classification
  python main.py --input data.xlsx --output output/
  
  # AI-only mode (Grok extracts everything)
  python main.py --input data.xlsx --output output/ --ai-only
  
  # Without AI classification (regex only, no Grok)
  python main.py --input data.xlsx --output output/ --no-grok
  
  # Use Kima/Maagarim gazetteer (48k+ places)
  python main.py --input data.xlsx --output output/ --use-kima
  
  # Test with limited manuscripts
  python main.py --input data.xlsx --output output/ --limit 10
  
  # Full configuration
  python main.py --input data.xlsx --output output/ \\
    --gazetteer locations.csv --api-key YOUR_KEY \\
    --workers 10 --timeout 45
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Input Excel file path (.xlsx)'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output directory for results'
    )
    
    # Extraction modes
    mode_group = parser.add_argument_group('Extraction Modes')
    mode_group.add_argument(
        '--ai-only',
        action='store_true',
        help='Use AI (Grok) for complete extraction instead of regex patterns'
    )
    mode_group.add_argument(
        '--no-grok',
        action='store_true',
        help='Disable Grok classification (regex extraction only)'
    )
    mode_group.add_argument(
        '--use-kima',
        action='store_true',
        help='Use Kima/Maagarim gazetteer for location extraction (48k+ places)'
    )
    
    # Optional data
    parser.add_argument(
        '--gazetteer', '-g',
        help='Location gazetteer CSV file path (optional)'
    )
    
    # API configuration
    api_group = parser.add_argument_group('API Configuration')
    api_group.add_argument(
        '--api-key',
        help='Grok API key (or set GROK_SECRET environment variable)'
    )
    api_group.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of parallel API workers (default: 8)'
    )
    api_group.add_argument(
        '--timeout',
        type=int,
        default=35,
        help='API request timeout in seconds (default: 35)'
    )
    api_group.add_argument(
        '--retries',
        type=int,
        default=3,
        help='Number of API retry attempts (default: 3)'
    )
    
    # Processing options
    proc_group = parser.add_argument_group('Processing Options')
    proc_group.add_argument(
        '--limit',
        type=int,
        help='Limit number of manuscripts to process (for testing)'
    )
    proc_group.add_argument(
        '--min-token-length',
        type=int,
        default=2,
        help='Minimum token length for location extraction (default: 2)'
    )
    proc_group.add_argument(
        '--max-location-tokens',
        type=int,
        default=6,
        help='Maximum tokens in location name (default: 6)'
    )
    
    # Ontology namespaces (advanced)
    onto_group = parser.add_argument_group('Ontology Configuration (Advanced)')
    onto_group.add_argument(
        '--base-namespace',
        default='http://data.hebrewmanuscripts.org/',
        help='Base namespace URI'
    )
    onto_group.add_argument(
        '--hm-namespace',
        default='http://www.ontology.org.il/HebrewManuscripts/2025-08-19#',
        help='Hebrew Manuscripts namespace URI'
    )
    
    return parser.parse_args()


def get_api_key(args):
    """
    Get API key from multiple sources (priority order):
    1. CLI argument (--api-key)
    2. secrets.txt file (project root or src/ directory)
    3. Environment variable (GROK_SECRET)
    """
    # 1. Check CLI argument
    if args.api_key:
        return args.api_key
    
    # 2. Check secrets.txt file in multiple locations
    project_root = Path(__file__).parent
    secrets_locations = [
        project_root / "secrets.txt",
        project_root / "src" / "secrets.txt",
    ]
    
    for secrets_file in secrets_locations:
        if secrets_file.exists():
            try:
                content = secrets_file.read_text().strip()
                if content:
                    # Handle both formats:
                    # Format 1: GROK_SECRET=xai-abc123...
                    # Format 2: xai-abc123... (plain API key)
                    if content.startswith("GROK_SECRET="):
                        api_key = content.split("=", 1)[1].strip()
                    else:
                        api_key = content
                    
                    if api_key:
                        print(f"[OK] API key loaded from {secrets_file}")
                        return api_key
            except Exception as e:
                print(f"[WARNING] Could not read {secrets_file}: {e}")
    
    # 3. Check environment variable
    api_key = os.getenv('GROK_SECRET')
    if api_key:
        print("[OK] API key loaded from GROK_SECRET environment variable")
        return api_key
    
    # No API key found
    print("[WARNING] No Grok API key provided")
    print("  Options:")
    print("    1. Create secrets.txt file with format: GROK_SECRET=your-api-key")
    print("    2. Use --api-key argument")
    print("    3. Set GROK_SECRET environment variable")
    print("  API features will be disabled")
    
    return None


def validate_inputs(args):
    """Validate input arguments"""
    errors = []
    
    # Check input file exists
    if not os.path.exists(args.input):
        errors.append(f"Input file not found: {args.input}")
    elif not args.input.endswith('.xlsx'):
        errors.append(f"Input must be Excel (.xlsx) file: {args.input}")
    
    # Check output directory
    output_path = Path(args.output)
    if not output_path.exists():
        try:
            output_path.mkdir(parents=True, exist_ok=True)
            print(f"[OK] Created output directory: {args.output}")
        except Exception as e:
            errors.append(f"Cannot create output directory: {e}")
    
    # Check gazetteer if provided
    if args.gazetteer and not os.path.exists(args.gazetteer):
        errors.append(f"Gazetteer file not found: {args.gazetteer}")
    
    # Check API requirements
    api_key = get_api_key(args)
    if (args.ai_only or not args.no_grok) and not api_key:
        errors.append("Grok API key required for AI features (use --api-key or set GROK_SECRET)")
    
    # Check conflicting options
    if args.ai_only and args.no_grok:
        errors.append("Cannot use both --ai-only and --no-grok")
    
    if errors:
        print("\n[ERROR] Validation Errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


def main():
    """Main entry point"""
    args = parse_arguments()
    
    # Validate inputs
    validate_inputs(args)
    
    # Get API key
    api_key = get_api_key(args)
    
    # Build configuration
    config = Config(
        # Paths
        input_excel_path=args.input,
        output_dir=args.output,
        gazetteer_path=args.gazetteer,
        
        # Behavior
        min_token_length=args.min_token_length,
        max_location_tokens=args.max_location_tokens,
        use_grok=not args.no_grok,
        ai_only=args.ai_only,
        use_kima=args.use_kima,
        
        # API
        grok_api_key=api_key,
        grok_max_workers=args.workers,
        grok_retries=args.retries,
        grok_timeout=args.timeout,
        
        # Ontology
        base_namespace=args.base_namespace,
        hm_namespace=args.hm_namespace,
    )
    
    # Print configuration
    print("\n" + "="*80)
    print("CONFIGURATION")
    print("="*80)
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Gazetteer: {args.gazetteer or 'None'}")
    print(f"\nExtraction Mode:")
    if args.ai_only:
        print("  [AI-ONLY] Grok extracts all entities")
    elif args.no_grok:
        print("  [REGEX-ONLY] Pattern-based extraction (no AI)")
    else:
        print("  [HYBRID] Regex extraction + Grok classification")
    
    if args.use_kima:
        print(f"\nLocation Extraction:")
        print("  [KIMA] Using Kima/Maagarim gazetteer (48k+ places)")
        print(f"\nClassification Mode:")
        print("  [HYBRID] Hebrew patterns (fast) + AI fallback (accurate)")
    
    if args.limit:
        print(f"\n[TEST MODE] Limited to {args.limit} manuscripts")
    
    print("="*80 + "\n")
    
    # Run pipeline
    try:
        result = run_extraction_pipeline(
            config=config,
            max_manuscripts=args.limit
        )
        
        print("\n[SUCCESS] Extraction completed.")
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Interrupted by user")
        sys.exit(130)
        
    except Exception as e:
        print(f"\n\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

