"""
Pure Text Extraction Functions
All functions are pure - no side effects, deterministic output
"""

import re
from typing import List, Tuple, Optional, Set
from functools import lru_cache

from ..models.entities import ExtractedEntity, EntityType, ColophonInfo, Person


# ============================================================================
# DATE EXTRACTION - Pure Functions
# ============================================================================

# Hebrew date patterns (immutable constants)
HEB_YEAR_WORDS = ["שנת", "בשנת", "שנה"]
HEB_CIRCA = ["בקירוב", "סביב", "בערך", "כ", "כ\""]
HEB_CENTURY = ["מאה", "המאה"]
HEB_DECADE = ["שנות"]

RE_YEAR = r"(?<!\d)(?:שנת\s+)?(1[4-9][0-9]{2})(?!\d)"
RE_CENTURY_DIGIT = r"(?:ה?מאה\s+ה?)(1[4-9]|20)(?!\s*\d)"
RE_YEAR_RANGE = rf"{RE_YEAR}\s*(?:-|–|—|/|\\)\s*{RE_YEAR}"

DATE_REGEXES = [
    ("year_range", re.compile(RE_YEAR_RANGE, re.IGNORECASE)),
    ("gregorian_year", re.compile(RE_YEAR, re.IGNORECASE)),
    ("century_digit", re.compile(RE_CENTURY_DIGIT)),
]

HEBREW_MONTHS = frozenset([
    "תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר", "ניסן", 
    "אייר", "סיון", "תמוז", "אב", "אלול", "מרחשון"
])

# Common Hebrew words that are NOT locations (blacklist)
LOCATION_BLACKLIST = frozenset([
    # Compound prefixes that should never appear alone
    "תל",      # Always "תל אביב", never alone
    "בית",     # Usually "בית שאן", "בית לחם"
    "קרית",    # Usually "קרית ארבע", "קרית שמונה"
    
    # Common words often mistaken for places
    "תלמוד", "בתלמוד", "תלמידי", "תלמידים",  # Talmud, students
    "ישראל",   # Israel (ambiguous - person name vs. place)
    "יקום", "פורקן", "יזכור",  # Liturgical terms
    "ואני", "עומר", "האלה",    # Common words
    "פרוט", "קוטי",             # Not places
    "תלת", "התל",               # Partial words
    
    # Person names often confused with places
    "קארו", "פאנו",             # Yosef Karo, Menachem Azariah da Fano
    "אליהו", "משה", "יוסף",     # Common first names
    
    # Questionable low-frequency entries
    "קורי",                     # Not a known place
    
    # Hebrew months (duplicate check - already in HEBREW_MONTHS but add here too)
    "אייר",                     # Hebrew month, not a place
])


@lru_cache(maxsize=1000)
def is_valid_year(year_str: str) -> bool:
    """Pure function: Check if string represents a valid year"""
    try:
        year = int(year_str)
        return 1400 <= year <= 2100
    except (ValueError, TypeError):
        return False


def extract_dates(text: str) -> List[ExtractedEntity]:
    """
    Pure function: Extract all date entities from text
    
    Args:
        text: Input Hebrew text
        
    Returns:
        List of immutable ExtractedEntity objects
    """
    if not isinstance(text, str) or not text.strip():
        return []
    
    found_dates: List[ExtractedEntity] = []
    seen_values: Set[str] = set()
    
    for pattern_name, regex in DATE_REGEXES:
        for match in regex.finditer(text):
            value = match.group().strip()
            
            # Skip if already found
            if value in seen_values:
                continue
            
            # Validate extracted value
            if len(value) < 4 or value in HEBREW_MONTHS:
                continue
            
            # Create immutable entity
            entity = ExtractedEntity(
                value=value,
                entity_type=EntityType.DATE,
                confidence=0.9 if pattern_name == "year_range" else 0.85,
                context=text[max(0, match.start()-20):match.end()+20],
                start_pos=match.start(),
                end_pos=match.end()
            )
            
            found_dates.append(entity)
            seen_values.add(value)
    
    return found_dates


# ============================================================================
# LOCATION EXTRACTION - Pure Functions
# ============================================================================

def load_gazetteer(gazetteer_set: Set[str]) -> frozenset:
    """Pure function: Convert mutable set to immutable frozenset"""
    return frozenset(gazetteer_set)


def extract_locations(
    text: str, 
    gazetteer: frozenset = frozenset(),
    max_tokens: int = 6,
    min_token_length: int = 2
) -> List[ExtractedEntity]:
    """
    Pure function: Extract location entities from text
    
    Args:
        text: Input Hebrew text
        gazetteer: Immutable set of known locations
        max_tokens: Maximum words in location name
        min_token_length: Minimum character length per token
        
    Returns:
        List of immutable ExtractedEntity objects
    """
    if not isinstance(text, str) or not text.strip():
        return []
    
    # Hebrew unicode range pattern (include hyphens for compound names like תל אביב-יפו)
    HEB_PATTERN = r'[\u0590-\u05FF\-]+'
    
    # Tokenize and clean up
    raw_tokens = re.findall(HEB_PATTERN, text)
    # Remove tokens that are just hyphens
    tokens = [t for t in raw_tokens if t != '-' and not t.startswith('-') and not t.endswith('-')]
    locations: List[ExtractedEntity] = []
    seen_values: Set[str] = set()
    
    # FIRST: Extract multi-token phrases (higher priority than single words)
    multi_word_tokens = set()  # Track tokens that are part of multi-word phrases
    
    for n in range(max_tokens, 1, -1):  # Start with longest phrases
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            
            # Check original phrase
            if phrase in gazetteer and phrase not in seen_values:
                entity = ExtractedEntity(
                    value=phrase,
                    entity_type=EntityType.LOCATION,
                    confidence=0.95,
                    context=text
                )
                locations.append(entity)
                seen_values.add(phrase)
                # Mark these tokens as part of a multi-word phrase
                for j in range(i, i+n):
                    multi_word_tokens.add(tokens[j])
            else:
                # Try stripping prefix from first token
                first_token = tokens[i]
                stripped_first = _strip_hebrew_prefixes(first_token)
                if stripped_first != first_token:
                    stripped_phrase = " ".join([stripped_first] + tokens[i+1:i+n])
                    if stripped_phrase in gazetteer and stripped_phrase not in seen_values:
                        entity = ExtractedEntity(
                            value=stripped_phrase,
                            entity_type=EntityType.LOCATION,
                            confidence=0.90,
                            context=text
                        )
                        locations.append(entity)
                        seen_values.add(stripped_phrase)
                        # Mark these tokens as part of a multi-word phrase
                        for j in range(i, i+n):
                            multi_word_tokens.add(tokens[j])
    
    # SECOND: Extract single tokens (only if not part of multi-word phrase)
    for token in tokens:
        # Skip if already part of a multi-word phrase
        if token in multi_word_tokens:
            continue
            
        if len(token) >= min_token_length and token not in HEBREW_MONTHS:
            # Check blacklist FIRST (before gazetteer)
            if token in LOCATION_BLACKLIST:
                continue
            
            stripped_for_check = _strip_hebrew_prefixes(token)
            if stripped_for_check in LOCATION_BLACKLIST:
                continue
            
            # Check original token in gazetteer
            if token in gazetteer:
                if token not in seen_values:
                    entity = ExtractedEntity(
                        value=token,
                        entity_type=EntityType.LOCATION,
                        confidence=0.9,
                        context=text
                    )
                    locations.append(entity)
                    seen_values.add(token)
            else:
                # Try stripping Hebrew prefixes (ב, ל, מ, ה, ו, כ, ש)
                stripped_token = _strip_hebrew_prefixes(token)
                if stripped_token != token and stripped_token in gazetteer:
                    # Check blacklist again
                    if stripped_token in LOCATION_BLACKLIST:
                        continue
                    if stripped_token not in seen_values:
                        entity = ExtractedEntity(
                            value=stripped_token,
                            entity_type=EntityType.LOCATION,
                            confidence=0.85,
                            context=text
                        )
                        locations.append(entity)
                        seen_values.add(stripped_token)
                # Fallback to heuristic matching (disabled for now to reduce false positives)
                # elif _looks_like_location(token):
                #     if token not in seen_values:
                #         entity = ExtractedEntity(
                #             value=token,
                #             entity_type=EntityType.LOCATION,
                #             confidence=0.6,
                #             context=text
                #         )
                #         locations.append(entity)
                #         seen_values.add(token)
    
    return locations


def _strip_hebrew_prefixes(token: str) -> str:
    """
    Pure helper: Strip Hebrew prefixes from token
    
    Hebrew prefixes: ב (in), ל (to), מ (from), ה (the), ו (and), כ (like), ש (that)
    """
    prefixes = ['ב', 'ל', 'מ', 'ה', 'ו', 'כ', 'ש']
    
    for prefix in prefixes:
        # Require at least 2 characters after prefix (e.g., בתל → תל is OK)
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            # Check if next character is also a prefix (e.g., "וב", "מה")
            remaining = token[1:]
            if len(remaining) > 1 and remaining[0] in prefixes:
                # Double prefix case (e.g., "מה", "וב")
                if len(remaining) > 2:
                    return remaining[1:]  # Strip both prefixes
            return remaining
    
    return token


def _looks_like_location(token: str) -> bool:
    """Pure helper: Heuristic check if token looks like a place name"""
    # Strip prefixes first
    stripped = _strip_hebrew_prefixes(token)
    
    # Place names often start with certain prefixes
    place_prefixes = ["ירושל", "תל", "חיפ", "בית", "קרית"]
    return any(stripped.startswith(prefix) for prefix in place_prefixes)


def extract_locations_with_kima(
    text: str,
    kima_gazetteer
) -> List[ExtractedEntity]:
    """
    Pure function: Extract location entities using Kima/Maagarim gazetteer
    with context-aware validation to filter false positives
    
    Args:
        text: Input Hebrew text
        kima_gazetteer: KimaGazetteer instance with loaded data
        
    Returns:
        List of immutable ExtractedEntity objects with rich metadata
    """
    if not isinstance(text, str) or not text.strip():
        return []
    
    # Import validators
    from .location_validator import (
        validate_location_extraction,
        get_location_confidence,
        is_blacklisted
    )
    
    # Hebrew unicode range pattern (include hyphens for compound names)
    HEB_PATTERN = r'[\u0590-\u05FF\-]+'
    
    # Tokenize and clean up
    raw_tokens = re.findall(HEB_PATTERN, text)
    # Remove tokens that are just hyphens
    tokens = [t for t in raw_tokens if t != '-' and not t.startswith('-') and not t.endswith('-')]
    
    locations: List[ExtractedEntity] = []
    seen_values: Set[str] = set()
    
    # Try multi-token phrases first (up to 6 tokens)
    max_tokens = 6
    for n in range(max_tokens, 0, -1):  # Start with longest phrases
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i+n])
            
            # PRE-FILTER: Check if SOURCE PHRASE is blacklisted BEFORE Kima lookup
            # This prevents common words like "נושא" (subject) from being looked up
            phrase_base = phrase.split()[0] if ' ' in phrase else phrase
            
            if is_blacklisted(phrase_base):
                # Skip blacklisted source words
                continue
            
            # Try Kima lookup (includes variants, forms, and prefix stripping)
            place_data = kima_gazetteer.lookup(phrase)
            
            if place_data and place_data['hebrew'] not in seen_values:
                canonical_name = place_data['hebrew']
                
                # VALIDATE: Check if this is a legitimate location in context
                # (filters false positives like Hebrew months, person names, etc.)
                
                # Calculate context-aware confidence first
                confidence = get_location_confidence(canonical_name, text)
                
                # Stricter validation for short/ambiguous words
                canonical_base = re.sub(r'\s*\([^)]+\)\s*$', '', canonical_name).strip()
                
                # For single-word locations without country suffix, require high confidence
                if ' ' not in canonical_base and '(' not in canonical_name:
                    # Single word without country - must have strong context
                    is_valid = validate_location_extraction(
                        word=canonical_name,
                        text=text,
                        min_length=4,  # Longer minimum for single words
                        require_context=True  # REQUIRE location context
                    )
                    min_confidence = 0.6  # High threshold
                else:
                    # Multi-word or has country suffix - can be more lenient
                    is_valid = validate_location_extraction(
                        word=canonical_name,
                        text=text,
                        min_length=3,
                        require_context=False
                    )
                    min_confidence = 0.4  # Lower threshold
                
                if not is_valid or confidence < min_confidence:
                    # Skip this false positive
                    continue
                
                entity = ExtractedEntity(
                    value=canonical_name,  # Canonical Hebrew name
                    entity_type=EntityType.LOCATION,
                    confidence=confidence,  # Context-aware confidence
                    context=text,
                    metadata={
                        'wikidata': place_data.get('wikidata', ''),
                        'viaf': place_data.get('viaf', ''),
                        'geonames': place_data.get('geonames', ''),
                        'lat': place_data.get('lat', ''),
                        'lon': place_data.get('lon', ''),
                        'romanized': place_data.get('romanized', ''),
                        'description': place_data.get('description', ''),
                        'source': 'kima',
                        'matched_phrase': phrase  # Original phrase that matched
                    }
                )
                locations.append(entity)
                seen_values.add(canonical_name)
    
    return locations


# ============================================================================
# COLOPHON DETECTION - Pure Functions
# ============================================================================

COLOPHON_MARKERS = frozenset([
    r"נשלם", r"נכתב", r"וסיימתיו", r"השלמתי",
    r"תם ונשלם", r"ע\"י.*בר", r"ביד.*בן",
    r"כתבתיו אני", r"נכתב.*ביד"
])

COMPLETION_PATTERNS = frozenset([
    r"נשלם", r"תם ונשלם", r"השלמתי", r"וסיימתי"
])


def detect_colophon(text: str) -> bool:
    """
    Pure function: Detect if text contains colophon markers
    
    Args:
        text: Input Hebrew text
        
    Returns:
        Boolean indicating colophon presence
    """
    if not isinstance(text, str) or not text.strip():
        return False
    
    return any(re.search(marker, text, re.IGNORECASE) 
               for marker in COLOPHON_MARKERS)


def extract_colophon_info(text: str) -> Optional[ColophonInfo]:
    """
    Pure function: Extract structured colophon information
    
    Args:
        text: Input Hebrew text
        
    Returns:
        Immutable ColophonInfo or None
    """
    if not detect_colophon(text):
        return None
    
    has_completion = any(re.search(pattern, text, re.IGNORECASE)
                        for pattern in COMPLETION_PATTERNS)
    
    scribe_name = extract_scribe_name(text)
    
    return ColophonInfo(
        text=text,
        has_completion_marker=has_completion,
        scribe_name=scribe_name
    )


# ============================================================================
# PERSON EXTRACTION - Pure Functions
# ============================================================================

SCRIBE_PATTERNS = [
    # "by the hand of X son of Y"
    r"ביד\s+([\u0590-\u05FF\s]+?)\s+בן\s+([\u0590-\u05FF\s]+?)(?:\s|$|[,.])",
    # "written by X son of Y"
    r"נכתב.*?(?:ע\"י|ביד)\s+([\u0590-\u05FF\s]+?)\s+בן\s+([\u0590-\u05FF\s]+?)(?:\s|$|[,.])",
    # "I, X son of Y, wrote"
    r"אני\s+([\u0590-\u05FF\s]+?)\s+בן\s+([\u0590-\u05FF\s]+?)\s+(?:כתבתי|העתקתי)",
    # "the young/junior X son of Y"
    r"הצעיר\s+([\u0590-\u05FF\s]+?)\s+בן\s+([\u0590-\u05FF\s]+?)(?:\s|$|[,.])",
]


def extract_scribe_name(text: str) -> Optional[str]:
    """
    Pure function: Extract scribe name using Hebrew patronymic patterns
    
    Args:
        text: Input Hebrew text
        
    Returns:
        Full scribe name or None
    """
    if not isinstance(text, str):
        return None
    
    for pattern in SCRIBE_PATTERNS:
        match = re.search(pattern, text)
        if match and len(match.groups()) >= 2:
            first_name = _normalize_hebrew_name(match.group(1))
            father_name = _normalize_hebrew_name(match.group(2))
            return f"{first_name} בן {father_name}"
    
    return None


def extract_person_mentions(text: str) -> List[Person]:
    """
    Pure function: Extract all person mentions from text
    
    Args:
        text: Input Hebrew text
        
    Returns:
        List of immutable Person objects
    """
    if not isinstance(text, str) or not text.strip():
        return []
    
    persons: List[Person] = []
    seen_names: Set[str] = set()
    
    # Pattern: X ben Y (Hebrew patronymic)
    pattern = r"([\u0590-\u05FF]{2,})\s+בן\s+([\u0590-\u05FF]{2,})"
    
    for match in re.finditer(pattern, text):
        first_name = _normalize_hebrew_name(match.group(1))
        father_name = _normalize_hebrew_name(match.group(2))
        full_name = f"{first_name} בן {father_name}"
        
        if full_name not in seen_names:
            person = Person(
                name=first_name,
                patronymic=father_name
            )
            persons.append(person)
            seen_names.add(full_name)
    
    return persons


def _normalize_hebrew_name(name: str) -> str:
    """Pure helper: Normalize Hebrew name text"""
    return re.sub(r'\s+', ' ', name.strip())


# ============================================================================
# WORK/TITLE EXTRACTION - Pure Functions
# ============================================================================

TITLE_PATTERNS = [
    r"ספר\s+([\u0590-\u05FF\s]{3,20})",    # "ספר X"
    r"חיבור\s+([\u0590-\u05FF\s]{3,20})",  # "חיבור X"
    r"פירוש\s+([\u0590-\u05FF\s]{3,20})", # "פירוש X"
]


def extract_work_title(text: str) -> Optional[str]:
    """
    Pure function: Extract work title from text
    
    Args:
        text: Input Hebrew text
        
    Returns:
        Title string or None
    """
    if not isinstance(text, str) or not text.strip():
        return None
    
    for pattern in TITLE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            title = _normalize_hebrew_name(match.group(1))
            if 3 < len(title) < 50:
                return title
    
    return None


# ============================================================================
# BATCH PROCESSING - Pure Functional Composition
# ============================================================================

def extract_all_entities(text: str, gazetteer: frozenset = frozenset()) -> dict:
    """
    Pure function: Extract all entity types at once
    Functional composition of extraction functions
    
    Args:
        text: Input Hebrew text
        gazetteer: Immutable location gazetteer
        
    Returns:
        Dictionary with all extracted entities
    """
    return {
        "dates": extract_dates(text),
        "locations": extract_locations(text, gazetteer),
        "persons": extract_person_mentions(text),
        "colophon": extract_colophon_info(text),
        "work_title": extract_work_title(text),
        "has_colophon": detect_colophon(text),
    }
