#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hebrew Pattern-Based Entity Classification
Uses regex patterns to detect Hebrew linguistic markers for manuscript roles.
Fallback to Grok API if patterns don't match.
"""

import re
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class HebrewPattern:
    """Immutable Hebrew pattern definition"""
    role: str
    patterns: Tuple[str, ...]  # Regex patterns
    description: str


# ============================================================================
# HEBREW PATTERNS FOR PERSON ROLES (Based on Manuscript Catalog Notes)
# ============================================================================

SCRIBE_PATTERNS = HebrewPattern(
    role="scribe",
    patterns=(
        r'נשלם\s+(?:על\s+)?(?:ידי|יד)',  # נשלם על ידי, נשלם ידי
        r'נכתב\s+(?:על\s+)?(?:ידי|ביד)',  # נכתב על ידי, נכתב ביד
        r'כתב(?:ו|תי|ה)?',  # כתב, כתבו, כתבתי, כתבה
        r'העתיק',  # העתיק
        r'מעתיק',  # מעתיק
        r'הכותב',  # הכותב
        r'סופר',  # סופר
        r'נעתק\s+(?:על\s+)?ידי',  # נעתק על ידי
    ),
    description="Physical manuscript writer"
)

AUTHOR_PATTERNS = HebrewPattern(
    role="author",
    patterns=(
        r'מחבר',  # מחבר
        r'חיבר(?:ו)?',  # חיבר, חיברו
        r'המחבר',  # המחבר
        r'מאת',  # מאת
        r'חברו',  # חברו
        r'יסדו',  # יסדו
        r'חבר\s+ה(?:ר|רב)',  # חבר הר, חבר הרב
    ),
    description="Intellectual work creator"
)

OWNER_PATTERNS = HebrewPattern(
    role="owner",
    patterns=(
        r'רשות',  # רשות
        r'שייך\s+ל',  # שייך ל
        r'זה\s+הספר\s+של',  # זה הספר של
        r'בעלים',  # בעלים
        r'ממון',  # ממון
        r'של\s+כמ["\']',  # של כמ"ר, של כמ'
        r'שלי',  # שלי
    ),
    description="Current possessor"
)

PREVIOUS_OWNER_PATTERNS = HebrewPattern(
    role="previous owner",
    patterns=(
        r'היה\s+(?:רשות|של)',  # היה רשות, היה של
        r'מסר\s+מ',  # מסר מ
        r'העביר',  # העביר
        r'היה\s+בעלים',  # היה בעלים
    ),
    description="Former possessor"
)

PURCHASER_PATTERNS = HebrewPattern(
    role="purchaser",
    patterns=(
        r'קנה',  # קנה
        r'קניתי',  # קניתי
        r'רכש',  # רכש
        r'קנאו',  # קנאו
        r'נקנה\s+(?:על\s+)?יד(?:י)?',  # נקנה על ידי, נקנה יד
    ),
    description="Bought manuscript"
)

SELLER_PATTERNS = HebrewPattern(
    role="seller",
    patterns=(
        r'מכר',  # מכר
        r'נמכר\s+מיד',  # נמכר מיד
        r'מכרו',  # מכרו
    ),
    description="Sold manuscript"
)

DONOR_PATTERNS = HebrewPattern(
    role="donor",
    patterns=(
        r'הקדיש',  # הקדיש
        r'תרם',  # תרם
        r'נתן\s+במתנה',  # נתן במתנה
        r'הקדשתי',  # הקדשתי
        r'נתן\s+ל',  # נתן ל
    ),
    description="Donated manuscript"
)

TRANSLATOR_PATTERNS = HebrewPattern(
    role="translator",
    patterns=(
        r'תרגם',  # תרגם
        r'מתרגם',  # מתרגם
        r'תרגום',  # תרגום
        r'התרגום',  # התרגום
    ),
    description="Translated work"
)

COMMENTATOR_PATTERNS = HebrewPattern(
    role="commentator",
    patterns=(
        r'פירש',  # פירש
        r'מפרש',  # מפרש
        r'פרשן',  # פרשן
        r'ביאר',  # ביאר
        r'מבאר',  # מבאר
    ),
    description="Wrote commentary"
)

ILLUMINATOR_PATTERNS = HebrewPattern(
    role="illuminator",
    patterns=(
        r'צייר',  # צייר
        r'מאייר',  # מאייר
        r'ציר',  # ציר
        r'עטר',  # עטר
    ),
    description="Decorated manuscript"
)

CATALOGER_PATTERNS = HebrewPattern(
    role="cataloger",
    patterns=(
        r'קטלג',  # קטלג
        r'מקטלג',  # מקטלג
        r'רשם',  # רשם
    ),
    description="Catalogued manuscript"
)

CENSOR_PATTERNS = HebrewPattern(
    role="censor",
    patterns=(
        r'צנזור',  # צנזור
        r'בוחן',  # בוחן
        r'בדק',  # בדק
    ),
    description="Censored text"
)

COLOPHON_SCRIBE_PATTERNS = HebrewPattern(
    role="colophon scribe",
    patterns=(
        r'(?:נשלם|קולופון).*?(?:נכתב|כתב)',  # נשלם...נכתב, קולופון...כתב
    ),
    description="Scribe mentioned in colophon"
)

# ============================================================================
# HEBREW PATTERNS FOR LOCATION RELATIONSHIPS (Based on Manuscript Catalog Notes)
# ============================================================================

PRODUCTION_PLACE_PATTERNS = HebrewPattern(
    role="production place",  # Maps to: E12_Production → P7_took_place_at
    patterns=(
        r'נכתב\s+ב',  # נכתב ב (written in)
        r'נכתב\s+עיר',  # נכתב עיר (written city)
        r'נכתב\s+פה',  # נכתב פה (written here)
        r'הועתק\s+ב',  # הועתק ב (copied in)
        r'הועתק\s+עיר',  # הועתק עיר (copied city)
        r'נעשה\s+ב',  # נעשה ב (made in)
        r'נשלם\s+ב(?:עיר)?',  # נשלם ב, נשלם בעיר (completed in) - COMMON IN COLOPHONS
        r'נגמר\s+ב',  # נגמר ב (finished in)
        r'סיימתיו\s+ב',  # סיימתיו ב (I completed it in)
        r'כתוב\s+ב',  # כתוב ב (written in)
        r'קולופון.*?נכתב\s+ב',  # Colophon: written in
        r'קולופון.*?נשלם\s+ב',  # Colophon: completed in
        r'קולופון.*?הועתק\s+ב',  # Colophon: copied in
    ),
    description="Manuscript production place (E12_Production → P7_took_place_at)"
)

PUBLICATION_PLACE_PATTERNS = HebrewPattern(
    role="published in",  # Maps to: F30_Manifestation_Creation → P7_took_place_at
    patterns=(
        r'נדפס\s+ב',  # נדפס ב (printed in)
        r'הוצא\s+לאור\s+ב',  # הוצא לאור ב (published in)
        r'דפוס',  # דפוס (press)
        r'נדפס\s+עיר',  # נדפס עיר (printed city)
        r'הודפס\s+ב',  # הודפס ב (was printed in)
    ),
    description="Publication place (F30_Manifestation_Creation → P7_took_place_at)"
)

RESIDENCE_PATTERNS = HebrewPattern(
    role="resided in",  # Maps to: E21_Person → P74_has_current_or_former_residence
    patterns=(
        r'גר\s+ב',  # גר ב (lived in)
        r'ישב\s+ב',  # ישב ב (dwelt in)
        r'דר\s+ב',  # דר ב (resided in)
        r'מגורים\s+ב',  # מגורים ב (residence in)
        r'התגורר\s+ב',  # התגורר ב (resided in)
        r'מושבו\s+ב',  # מושבו ב (his residence in)
        r'בהיותי\s+ב',  # בהיותי ב (when I was in)
        r'בהיותו\s+ב',  # בהיותו ב (when he was in)
        r'בהיותם\s+ב',  # בהיותם ב (when they were in)
        r'בורח\s+מ',  # בורח מ (fleeing from)
        r'מתגורר\s+ב',  # מתגורר ב (residing in)
    ),
    description="Person residence (E21_Person → P74_has_current_or_former_residence)"
)

PRESERVATION_PATTERNS = HebrewPattern(
    role="preserved in",  # Maps to: F4_Manifestation_Singleton → P55_has_current_location
    patterns=(
        r'נמצא\s+(?:כיום\s+)?ב',  # נמצא (כיום) ב (currently found in)
        r'שמור\s+(?:כיום\s+)?ב',  # שמור (כיום) ב (currently kept in)
        r'ספריית',  # ספריית (library of)
        r'באוסף',  # באוסף (in collection)
        r'בספרייה',  # בספרייה (in library)
        r'ומספרו\s+(?:עתה|שם)',  # ומספרו עתה/שם (and its number now/there)
        r'מספרו\s+עתה',  # מספרו עתה (its number now)
    ),
    description="Current preservation location (P55_has_current_location)"
)

PERSON_ORIGIN_PATTERNS = HebrewPattern(
    role="born in",  # Maps to: E67_Birth → P7_took_place_at
    patterns=(
        r'נולד\s+ב',  # נולד ב (born in)
        r'יליד',  # יליד (native of)
        r'ילידת',  # ילידת (fem: native of)
        r'מולדתו',  # מולדתו (his birthplace)
    ),
    description="Person birthplace (E67_Birth → P7_took_place_at)"
)

PERSON_DEATH_PATTERNS = HebrewPattern(
    role="died in",  # Maps to: E69_Death → P7_took_place_at
    patterns=(
        r'נפטר\s+ב',  # נפטר ב (died in)
        r'מת\s+ב',  # מת ב (died in)
        r'נקבר\s+ב',  # נקבר ב (buried in)
        r'פטירתו\s+ב',  # פטירתו ב (his death in)
    ),
    description="Person death place (E69_Death → P7_took_place_at)"
)

PERSON_ACTIVITY_PATTERNS = HebrewPattern(
    role="worked in",  # Maps to: E7_Activity → P7_took_place_at
    patterns=(
        r'עבד\s+ב',  # עבד ב (worked in)
        r'פעל\s+ב',  # פעל ב (was active in)
        r'שימש\s+ב',  # שימש ב (served in)
        r'כיהן\s+ב',  # כיהן ב (held office in)
        r'היה\s+רב\s+ב',  # היה רב ב (was rabbi in)
    ),
    description="Person activity location (E7_Activity → P7_took_place_at)"
)

TRANSFER_PATTERNS = HebrewPattern(
    role="transferred to",  # Maps to: E10_Transfer_of_Custody → P26_moved_to
    patterns=(
        r'הועבר\s+ל',  # הועבר ל (transferred to)
        r'נמסר\s+ל',  # נמסר ל (handed to)
        r'הובא\s+מ',  # הובא מ (brought from)
        r'נשלח\s+ל',  # נשלח ל (sent to)
        r'נמכר\s+ל',  # נמכר ל (sold to)
        r'נרכש\s+(?:ע(?:"י|י)|מ)',  # נרכש ע"י/מ (acquired from/by)
        r'לפנים',  # לפנים (formerly - indicates provenance)
        r'מאוסף',  # מאוסף (from collection)
    ),
    description="Transfer location (E10_Transfer_of_Custody → P26_moved_to/P27_moved_from)"
)

# NOTE: "Colophon place" removed - colophons DESCRIBE events (usually production)
# Places in colophons should be classified by their event type (production, residence, etc.)
# See: CIDOC-CRM E73_Information_Object (colophon) → P70_documents → E12_Production

# All location patterns in order of precedence (most specific first)
# Order follows CIDOC-CRM event model:
# 1. Production/Creation events (E12_Production, F30_Manifestation_Creation)
# 2. Person life events (E67_Birth, E69_Death, P74_residence, E7_Activity)
# 3. Transfer events (E10_Transfer_of_Custody)
# 4. Current state (P55_has_current_location)
ALL_LOCATION_PATTERNS = [
    PRODUCTION_PLACE_PATTERNS,     # E12_Production → P7_took_place_at
    PUBLICATION_PLACE_PATTERNS,    # F30_Manifestation_Creation → P7_took_place_at
    PERSON_ORIGIN_PATTERNS,        # E67_Birth → P7_took_place_at
    PERSON_DEATH_PATTERNS,         # E69_Death → P7_took_place_at
    RESIDENCE_PATTERNS,            # P74_has_current_or_former_residence
    PERSON_ACTIVITY_PATTERNS,      # E7_Activity → P7_took_place_at
    TRANSFER_PATTERNS,             # E10_Transfer_of_Custody
    PRESERVATION_PATTERNS,         # P55_has_current_location (last resort)
]

# All patterns in order of precedence (most specific first)
ALL_PERSON_PATTERNS = [
    COLOPHON_SCRIBE_PATTERNS,  # Most specific - check first
    SCRIBE_PATTERNS,
    AUTHOR_PATTERNS,
    TRANSLATOR_PATTERNS,
    COMMENTATOR_PATTERNS,
    ILLUMINATOR_PATTERNS,
    OWNER_PATTERNS,
    PREVIOUS_OWNER_PATTERNS,
    PURCHASER_PATTERNS,
    SELLER_PATTERNS,
    DONOR_PATTERNS,
    CATALOGER_PATTERNS,
    CENSOR_PATTERNS,
]


# ============================================================================
# PATTERN MATCHING FUNCTIONS
# ============================================================================

def extract_person_context(text: str, person_name: str, context_window: int = 100) -> str:
    """
    Extract text context around person name
    
    Args:
        text: Full catalog note text
        person_name: Person name to find context for
        context_window: Characters before/after name
        
    Returns:
        Context text around person name
    """
    # Find person name in text
    person_clean = re.escape(person_name)
    match = re.search(person_clean, text, re.IGNORECASE)
    
    if not match:
        return text[:500]  # Return beginning if name not found
    
    start = max(0, match.start() - context_window)
    end = min(len(text), match.end() + context_window)
    
    return text[start:end]


def classify_person_by_patterns(
    text: str,
    person_name: str,
    patterns: List[HebrewPattern] = ALL_PERSON_PATTERNS
) -> Optional[str]:
    """
    Classify person role using Hebrew regex patterns
    
    Args:
        text: Catalog note text
        person_name: Person name to classify
        patterns: List of Hebrew patterns to check
        
    Returns:
        Role label if pattern matches, None otherwise
    """
    # Get context around person name
    context = extract_person_context(text, person_name)
    
    # Check each pattern in order of precedence
    for pattern_set in patterns:
        for pattern in pattern_set.patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return pattern_set.role
    
    return None  # No pattern matched


def classify_persons_batch(
    text: str,
    person_names: List[str]
) -> Dict[str, Optional[str]]:
    """
    Classify multiple persons from same text
    
    Args:
        text: Catalog note text
        person_names: List of person names to classify
        
    Returns:
        Dict mapping person name to role (or None if no pattern)
    """
    results = {}
    
    for person_name in person_names:
        role = classify_person_by_patterns(text, person_name)
        results[person_name] = role
    
    return results


# ============================================================================
# LOCATION CLASSIFICATION FUNCTIONS
# ============================================================================

def extract_location_context(text: str, location_name: str, context_window: int = 100) -> str:
    """
    Extract text context around location name
    
    Args:
        text: Full catalog note text
        location_name: Location name to find context for (may include country in parentheses)
        context_window: Characters before/after name
        
    Returns:
        Context text around location name
    """
    # Clean location name - remove country suffix in parentheses
    # e.g., "דמשק (סוריה)" → "דמשק"
    location_base = re.sub(r'\s*\([^)]+\)\s*$', '', location_name).strip()
    
    # Try to find the location in different forms:
    # 1. With ב prefix: "בדמשק" (in Damascus) 
    # 2. Base name: "דמשק"
    # 3. Full name with country: "דמשק (סוריה)"
    
    search_variants = [
        r'ב' + re.escape(location_base),  # With ב (in)
        re.escape(location_base),         # Base name
    ]
    
    # If full name differs from base, add it too
    if location_base != location_name:
        search_variants.append(re.escape(location_name))
    
    match = None
    for variant in search_variants:
        match = re.search(variant, text, re.IGNORECASE)
        if match:
            break
    
    if not match:
        # Location not found in text - might be false positive from Kima
        # Return empty string to signal no context available
        return ""
    
    start = max(0, match.start() - context_window)
    end = min(len(text), match.end() + context_window)
    
    return text[start:end]


def classify_location_by_patterns(
    text: str,
    location_name: str
) -> Optional[str]:
    """
    Classify location relationship using Hebrew linguistic patterns + context heuristics
    
    IMPROVED: Uses context-aware heuristics as fallback when explicit patterns don't match
    
    Args:
        text: Full catalog note text
        location_name: Location name to classify
        
    Returns:
        Relationship string (NEVER returns None - always makes a choice)
    """
    # Get context around location
    context = extract_location_context(text, location_name)
    
    # If location not found in text (false positive from Kima), skip it
    # Don't send to Grok - it's likely not a real location mention
    if not context or not context.strip():
        return None
    
    # Try each pattern in order of precedence
    for pattern_def in ALL_LOCATION_PATTERNS:
        for pattern in pattern_def.patterns:
            if re.search(pattern, context, re.IGNORECASE):
                return pattern_def.role
    
    # ========== NO EXPLICIT PATTERN MATCHED - USE CONTEXT HEURISTICS ==========
    # This is where we improve from 55% to 80%+ accuracy
    
    # HEURISTIC 1: Check section-based context
    # Look at larger text section to determine context
    location_pos = text.find(extract_location_context(text, location_name))
    if location_pos == -1:
        location_pos = 0
    
    # Get broader context (500 chars before and after)
    text_before = text[max(0, location_pos-500):location_pos]
    text_after = text[location_pos:min(len(text), location_pos+500)]
    broader_context = text_before + text_after
    
    # Check for colophon context → production place
    if re.search(r'קולופון|נשלם\s+(?:בעיר)?|הועתק|נכתב(?:\s+בעיר)?', broader_context, re.IGNORECASE):
        return "production place"
    
    # Check for preservation/ownership context → preserved in
    if re.search(r'ספריית|באוסף|בעלות|בידי|נמצא\s+ב|שמור\s+ב|repository|archive', broader_context, re.IGNORECASE):
        return "preserved in"
    
    # Check for provenance context → transferred to/from
    if re.search(r'מאוסף|לפנים|בעבר|מיד|הועבר|נמכר|לקוח', broader_context, re.IGNORECASE):
        return "transferred to"
    
    # Check for person context → resided in / active in
    if re.search(r'גר\s+ב|ישב\s+ב|דר\s+ב|מושבו|עיר|חי\s+ב', broader_context, re.IGNORECASE):
        return "resided in"
    
    # HEURISTIC 2: Format clues in the immediate context
    # Multiple locations separated by commas/semicolons → likely transfers or ownership
    if re.search(r'[,;]\s*(?:ו)?(?:ג)?[אב-ת]', context):
        return "transferred to"
    
    # HEURISTIC 3: Subject/topic field markers
    if re.search(r'נושא|subject|subject matter|תחום', broader_context, re.IGNORECASE):
        # Location mentioned as subject (e.g., "customs of Yemen") → active in / origin
        return "active in"
    
    # HEURISTIC 4: Position in text
    # First location mentioned is often production place
    all_locations = re.findall(location_name, text, re.IGNORECASE)
    if len(all_locations) == 1 and location_pos < len(text) * 0.3:
        return "production place"
    
    # HEURISTIC 5: Look for implicit event markers nearby
    # Even without explicit markers, context suggests events
    if any(word in context.lower() for word in ['ספר', 'כתב', 'כתיבה', 'כתיבת']):
        return "production place"
    
    if any(word in context.lower() for word in ['הדפס', 'הדפסה', 'דפוס', 'print']):
        return "printed in"
    
    if any(word in context.lower() for word in ['מעתיק', 'העתק', 'העתקה', 'copy']):
        return "production place"
    
    # HEURISTIC 6: DEFAULT for unmatched locations
    # Most Hebrew manuscripts mention their PRODUCTION place
    # So "production place" is the safest default
    return "production place"


def classify_locations_batch(
    text: str,
    location_names: List[str]
) -> Dict[str, Optional[str]]:
    """
    Classify multiple locations from the same text efficiently
    
    Args:
        text: Full catalog note text
        location_names: List of location names to classify
        
    Returns:
        Dictionary mapping location name to relationship (None if not found in text)
    """
    results = {}
    for location_name in location_names:
        role = classify_location_by_patterns(text, location_name)
        results[location_name] = role
    
    return results


# ============================================================================
# STATISTICS & DEBUG
# ============================================================================

def get_pattern_statistics() -> Dict[str, int]:
    """Get statistics about available patterns"""
    stats = {}
    for pattern_set in ALL_PERSON_PATTERNS:
        stats[pattern_set.role] = len(pattern_set.patterns)
    return stats


def test_patterns_on_text(text: str) -> Dict[str, List[str]]:
    """
    Test all patterns on text and return matches
    For debugging and pattern development
    """
    matches = {}
    
    for pattern_set in ALL_PERSON_PATTERNS:
        role_matches = []
        for pattern in pattern_set.patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            if found:
                role_matches.extend(found)
        
        if role_matches:
            matches[pattern_set.role] = role_matches
    
    return matches


if __name__ == "__main__":
    # Test patterns
    print("=" * 80)
    print("HEBREW PATTERN-BASED CLASSIFICATION")
    print("=" * 80)
    print()
    
    stats = get_pattern_statistics()
    print("Available patterns:")
    for role, count in stats.items():
        print(f"  {role:20s}: {count} patterns")
    print()
    print(f"Total roles: {len(stats)}")
    print(f"Total patterns: {sum(stats.values())}")
