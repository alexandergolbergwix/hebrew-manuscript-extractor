"""
Location Validation Module

Filters false positives from Kima gazetteer by checking context.
Hebrew manuscripts contain many ambiguous words that match place names
but are actually dates, person names, or common words.
"""

import re
from typing import Optional, Set

# ============================================================================
# HEBREW BLACKLIST - Words that should NEVER be treated as locations
# ============================================================================

# Hebrew months (absolute blacklist - these are NEVER locations in our context)
HEBREW_MONTHS = frozenset([
    "ניסן", "אייר", "סיון", "תמוז", "אב", "אלול",
    "תשרי", "חשון", "כסלו", "טבת", "שבט", "אדר",
    "אדר א", "אדר ב", "ירח"  # ירח = month (generic)
])

# Common Hebrew words that happen to match place names
COMMON_HEBREW_WORDS = frozenset([
    # Pronouns and particles
    "אני", "או", "אן", "אם", "בר", "מר", "נר",
    
    # Date-related terms
    "פרט", "סעד", "שנה", "יום", "ירח",
    
    # Titles and honorifics
    "רב", "מור", "מר", "רבי", "חכם",
    
    # Person name elements (common surnames that match places)
    "צמח", "נחם", "אמר", "עזר", "אשר", "נעם",
    "עומר", "שחר", "קדם", "קדמה", "עילם",
    "אור", "עידן", "סעדיה", "עזריה", "מנחם",
    
    # Common nouns - CRITICAL false positives!
    "ספר", "ספאר", "עיר", "קהל", "בית",
    "מים", "אש", "רוח", "עפר",
    "נושא",  # ← CRITICAL! "subject/topic" matches "Neuss (Germany)" in EVERY manuscript!
    "בכתבי", # "in writing" matches "Thebes (Greece)"
    "כתב", "כתבו", "כתבי",
    "מנחת",  # "offering" matches place names
    
    # Prepositions and common particles
    "מן", "על", "אל", "את", "עם", "של",
    "ב", "ל", "מ", "כ", "ה", "ו", "ש",
    
    # Astrological/celestial (sometimes in dates)
    "ירח", "שמש", "צדק", "נוגה", "שבתאי",
    
    # Single/two letter words (too ambiguous)
    "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט", "י",
    "אב", "אג", "אד", "אה", "אז", "או", "אי", "בא",
    "בה", "בו", "גב", "דב", "הב", "וב", "זב",
])

# Phrases that indicate NON-location context
NON_LOCATION_CONTEXTS = frozenset([
    # Date formulas
    r'לפרט\s+\w+',  # לפרט אמור = according to the count of [date]
    r'לשטרות\s+\w+',  # Seleucid era dating
    r'בשנת\s+\w+',  # in the year
    r'שנת\s+\w+',  # year of
    
    # Month indicators  
    r'מר"ח',  # מראש חדש = from beginning of month
    r'ר"ח',  # ראש חדש = beginning of month
    r'חדש\s+\w+',  # month of
    r'בחדש\s+\w+',  # in month of
    
    # Person name contexts
    r'בן\s+\w+',  # son of
    r'בר\s+\w+',  # son of (Aramaic)
    r'בת\s+\w+',  # daughter of
    r'רבי\s+\w+',  # Rabbi
    r'הרב\s+\w+',  # the Rabbi
    r'ר\'\s*\w+',  # R' (Rabbi abbreviation)
    r'מאת\s+\w+',  # by (author)
    r'אמר\s+\w+',  # said (introduces speaker)
])

# Phrases that DO indicate location context
LOCATION_CONTEXT_INDICATORS = frozenset([
    # With ב (in)
    r'נכתב\s+ב',  # written in
    r'נשלם\s+ב',  # completed in
    r'הועתק\s+ב',  # copied in
    r'נדפס\s+ב',  # printed in
    r'בהיותי\s+ב',  # when I was in
    r'בהיותו\s+ב',  # when he was in
    r'גר\s+ב',  # lived in
    r'ישב\s+ב',  # dwelt in
    
    # With מ (from) - movement from location
    r'בורח\s+מ',  # fleeing from
    r'יצא\s+מ',  # left from
    r'בא\s+מ',  # came from
    r'עלה\s+מ',  # went up from
    r'נסע\s+מ',  # traveled from
    
    # Location with country suffix pattern
    r'מ\w+\s+\([\w\s]+\)',  # מקום (מדינה) - place with country in parentheses
    
    # Repository/collection
    r'ספריית\s+',  # library of
    r'באוסף\s+',  # in collection of
    r'במוזיאון\s+',  # in museum of
    
    # Explicit place indicators
    r'בעיר\s+',  # in the city of
    r'בארץ\s+',  # in the land of
    r'במדינת\s+',  # in the state/country of
    r'לפנים\s+',  # formerly (provenance)
])


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def is_blacklisted(word: str) -> bool:
    """
    Check if word is in blacklist (should never be treated as location)
    
    Args:
        word: Hebrew word to check
        
    Returns:
        True if word is blacklisted
    """
    word_clean = word.strip()
    
    # Remove nikud (vowel points) for comparison
    word_no_nikud = re.sub(r'[\u0591-\u05C7]', '', word_clean)
    
    return (
        word_no_nikud in HEBREW_MONTHS or
        word_no_nikud in COMMON_HEBREW_WORDS or
        len(word_no_nikud) <= 2  # Too short to be reliable
    )


def is_in_date_context(text: str, position: int, window: int = 50) -> bool:
    """
    Check if position in text is within a date/chronological context
    
    Args:
        text: Full text
        position: Position of potential location
        window: Characters before/after to check
        
    Returns:
        True if in date context
    """
    start = max(0, position - window)
    end = min(len(text), position + window)
    context = text[start:end]
    
    for pattern in NON_LOCATION_CONTEXTS:
        if re.search(pattern, context):
            return True
    
    return False


def is_in_person_name_context(text: str, position: int, window: int = 30) -> bool:
    """
    Check if position is within a person name context
    
    Args:
        text: Full text
        position: Position of potential location
        window: Characters to check
        
    Returns:
        True if appears to be part of person name
    """
    start = max(0, position - window)
    end = min(len(text), position + window)
    context = text[start:end]
    
    # Check for person name indicators
    person_indicators = [
        r'בן\s+\w+', r'בר\s+\w+', r'בת\s+\w+',
        r'רבי\s+\w+', r'הרב\s+\w+', r'ר\'\s*\w+',
        r'מאת\s+\w+', r'אמר\s+\w+', r'כתב\s+\w+',
        r'\w+\s+בן\s+', r'\w+\s+בר\s+',
    ]
    
    for pattern in person_indicators:
        if re.search(pattern, context):
            return True
    
    return False


def has_location_context_indicator(text: str, word: str, window: int = 100) -> bool:
    """
    Check if word appears with clear location context indicators
    
    Args:
        text: Full text
        word: Word to find
        window: Context window size
        
    Returns:
        True if has strong location indicators nearby
    """
    # Find word position
    # Clean word - remove country suffix in parentheses if present
    word_base = re.sub(r'\s*\([^)]+\)\s*$', '', word).strip()
    
    # Try multiple search patterns
    search_patterns = [
        r'ב' + re.escape(word_base),  # With ב prefix
        r'\b' + re.escape(word_base) + r'\b',  # Exact word
    ]
    
    position = -1
    for pattern in search_patterns:
        match = re.search(pattern, text)
        if match:
            position = match.start()
            break
    
    if position == -1:
        return False  # Word not found
    
    # Check context around position
    start = max(0, position - window)
    end = min(len(text), position + window)
    context = text[start:end]
    
    # Look for location indicators
    for indicator in LOCATION_CONTEXT_INDICATORS:
        if re.search(indicator, context):
            return True
    
    # Check if word has country suffix (strong location indicator)
    if re.search(r'\s*\([א-ת\s,]+\)\s*$', word):
        return True
    
    return False


def validate_location_extraction(
    word: str,
    text: str,
    min_length: int = 3,
    require_context: bool = True
) -> bool:
    """
    Validate if extracted word is actually a location in context
    
    Args:
        word: Potential location word
        text: Full text context
        min_length: Minimum word length to consider
        require_context: If True, require location context indicators
        
    Returns:
        True if word passes validation as legitimate location
    """
    word_clean = word.strip()
    
    # Remove country suffix for analysis
    word_base = re.sub(r'\s*\([^)]+\)\s*$', '', word_clean).strip()
    
    # Rule 1: Check blacklist (absolute veto)
    if is_blacklisted(word_base):
        return False
    
    # Rule 2: Minimum length check
    if len(word_base) < min_length:
        return False
    
    # Rule 3: Find word position in text
    word_escaped = re.escape(word_base)
    match = re.search(r'\b' + word_escaped + r'\b', text)
    
    if not match:
        # Try with ב prefix
        match = re.search(r'ב' + word_escaped, text)
    
    if not match:
        # Word not in text (might be from MARC field) - allow but with caution
        # Only accept if word has country suffix (structured data indicator)
        return bool(re.search(r'\s*\([^)]+\)\s*$', word_clean))
    
    position = match.start()
    
    # Rule 4: Check for disqualifying contexts
    if is_in_date_context(text, position):
        return False
    
    if is_in_person_name_context(text, position):
        return False
    
    # Rule 5: If requiring context, check for location indicators
    if require_context:
        return has_location_context_indicator(text, word, window=100)
    
    # Passed all checks
    return True


def get_location_confidence(word: str, text: str) -> float:
    """
    Calculate confidence that extracted entity is really a location
    
    Based on:
    - Blacklist membership
    - Context analysis (date/person/location contexts)
    - Word characteristics (country suffix, multi-word)
    
    Returns:
        Float 0.0-1.0 representing confidence
    """
    word_base = word.split()[0] if ' ' in word else word
    
    # CRITICAL: Blacklist check
    if is_blacklisted(word_base):
        return 0.0
    
    # Start with base confidence
    confidence = 0.7  # Default moderate confidence
    
    # BOOST confidence for multi-word places (more likely real locations)
    if ' ' in word:
        confidence += 0.15
    
    # BOOST confidence for places with country suffix
    if re.search(r'\([^)]+\)', word):  # Has (Country) notation
        confidence += 0.20
    
    # CHECK FOR PERSON NAME FALSE POSITIVES
    # Pattern: "Name [בן|בר|בת] Patronymic"
    # If we see שם בן/בר pattern near our location, likely a person name match
    person_name_pattern = r'(?:יוסף|משה|דוד|יעקב|שמואל|עזרא|שלמה|יהודה|אברהם|אלעזר|יצחק|לוי|בנימין)\s+(?:בן|בר|בת)\s+\w+'
    if re.search(person_name_pattern, text, re.IGNORECASE):
        # Check if our word appears near a known person name
        for match in re.finditer(person_name_pattern, text, re.IGNORECASE):
            person_context = text[max(0, match.start()-30):match.end()+30]
            if word_base.lower() in person_context.lower():
                # Word appears in person name context - likely false positive!
                confidence *= 0.2  # Massive penalty
                break
    
    # PENALIZE if in date context
    if is_in_date_context(text, text.find(word_base)):
        confidence *= 0.1
    
    # PENALIZE if in person name context (but different pattern)
    if is_in_person_name_context(text, text.find(word_base)):
        confidence *= 0.15
    
    # BOOST if has location context indicator nearby
    if has_location_context_indicator(text, word):
        confidence *= 1.3
        confidence = min(confidence, 1.0)  # Cap at 1.0
    
    return max(0.0, min(confidence, 1.0))  # Clamp to 0-1

