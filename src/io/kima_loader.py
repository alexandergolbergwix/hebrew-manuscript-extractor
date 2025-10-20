"""
Kima & Maagarim Gazetteer Loader
Loads and indexes the three-file gazetteer system from Dr. Sinai Rosnik
"""
from typing import Dict, Optional
from pathlib import Path
import csv
from functools import lru_cache


class KimaGazetteer:
    """Unified gazetteer combining Kima places, variants, and Maagarim forms"""
    
    def __init__(self, data_dir: Path):
        """
        Initialize Kima gazetteer from data directory
        
        Args:
            data_dir: Path to directory containing the 3 TSV files
        """
        self.data_dir = Path(data_dir)
        
        # Master gazetteer: canonical_name → place_data
        self.places: Dict[str, dict] = {}
        
        # Variant lookup: variant_name → canonical_name
        self.variants: Dict[str, str] = {}
        
        # Textual forms lookup: textual_form → canonical_name
        self.textual_forms: Dict[str, str] = {}
        
        # Reverse index: PlaceId → canonical_name
        self.place_id_index: Dict[str, str] = {}
        
        # Load all data
        self._load_all()
    
    def _load_all(self):
        """Load all three files"""
        csv.field_size_limit(1000000)  # Handle large fields
        
        # Order matters: load places first to build id index
        self._load_master_gazetteer()
        self._load_variants()
        self._load_maagarim_forms()
    
    def _load_master_gazetteer(self):
        """Load Kima Places master file"""
        file_path = self.data_dir / "20251015 Kima places.tsv"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Kima places file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                canonical = row['primary_heb_full']
                place_id = row['Id']
                
                self.places[canonical] = {
                    'id': place_id,
                    'hebrew': canonical,
                    'romanized': row.get('primary_rom_full', ''),
                    'viaf': row.get('VIAF_ID', ''),
                    'geonames': row.get('Geoname_ID', ''),
                    'wikidata': row.get('WD', ''),
                    'lat': row.get('lat', ''),
                    'lon': row.get('lon', ''),
                    'description': row.get('Desc', ''),
                    'mazal_id': row.get('MAZAL_ID', ''),
                }
                
                # Build reverse index for variant lookup
                self.place_id_index[place_id] = canonical
    
    def _load_variants(self):
        """Load Kima Hebrew variants"""
        file_path = self.data_dir / "Kima-Hebrew-Variants-20250929.tsv"
        
        if not file_path.exists():
            print(f"  [WARNING] Kima variants file not found: {file_path}")
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                variant = row['variant']
                place_id = row['PlaceId']
                
                # Look up canonical name from place_id
                if place_id in self.place_id_index:
                    canonical = self.place_id_index[place_id]
                    self.variants[variant] = canonical
    
    def _load_maagarim_forms(self):
        """Load Maagarim textual forms"""
        file_path = self.data_dir / "Maagarim-Zurot-&-Arachim.tsv"
        
        if not file_path.exists():
            print(f"  [WARNING] Maagarim forms file not found: {file_path}")
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                canonical = row['word']  # EREKH (canonical value)
                textual_form = row['ZURA']  # ZURA (textual form)
                
                # Store mapping
                self.textual_forms[textual_form] = canonical
    
    @lru_cache(maxsize=10000)
    def lookup(self, text: str) -> Optional[dict]:
        """
        Unified lookup with cascading fallback
        
        Priority:
        1. Direct match in master gazetteer
        2. Textual form in Maagarim
        3. Variant name in Kima variants
        4. Prefix-stripped match (fallback)
        
        Args:
            text: Place name to lookup (may include prefixes)
        
        Returns:
            Place data dict or None if not found
        """
        # 1. Direct match in master gazetteer
        if text in self.places:
            return self.places[text]
        
        # 2. Textual form match (handles prefixed forms from Maagarim)
        if text in self.textual_forms:
            canonical = self.textual_forms[text]
            if canonical in self.places:
                return self.places[canonical]
        
        # 3. Variant name match
        if text in self.variants:
            canonical = self.variants[text]
            if canonical in self.places:
                return self.places[canonical]
        
        # 4. Prefix stripping fallback (existing logic)
        stripped = self._strip_prefixes(text)
        if stripped != text:
            # Try again with stripped version (recursive)
            result = self.lookup(stripped)
            if result:
                return result
        
        return None
    
    def _strip_prefixes(self, text: str) -> str:
        """
        Strip Hebrew prefixes (fallback for forms not in Maagarim)
        
        Hebrew prefixes: ב (in), ל (to), מ (from), ה (the), ו (and), כ (like), ש (that)
        """
        prefixes = ['ב', 'ל', 'מ', 'ה', 'ו', 'כ', 'ש']
        
        for prefix in prefixes:
            if text.startswith(prefix) and len(text) > len(prefix) + 1:
                remaining = text[1:]
                # Check for double prefix (e.g., "וב", "מה")
                if len(remaining) > 1 and remaining[0] in prefixes:
                    if len(remaining) > 2:
                        return remaining[1:]  # Strip both prefixes
                return remaining
        
        return text
    
    def get_frozenset(self) -> frozenset:
        """
        Get immutable set of all place names (for backward compatibility)
        
        Returns:
            Frozenset containing all known place names and variants
        """
        all_names = set()
        all_names.update(self.places.keys())
        all_names.update(self.variants.keys())
        all_names.update(self.textual_forms.keys())
        return frozenset(all_names)
    
    def get_statistics(self) -> dict:
        """
        Return statistics about loaded data
        
        Returns:
            Dict with counts and coverage percentages
        """
        total = len(self.places)
        
        return {
            'total_places': total,
            'total_variants': len(self.variants),
            'total_textual_forms': len(self.textual_forms),
            'total_lookups': total + len(self.variants) + len(self.textual_forms),
            'places_with_viaf': sum(1 for p in self.places.values() if p['viaf']),
            'places_with_geonames': sum(1 for p in self.places.values() if p['geonames']),
            'places_with_wikidata': sum(1 for p in self.places.values() if p['wikidata']),
            'places_with_coords': sum(1 for p in self.places.values() if p['lat'] and p['lon']),
        }


