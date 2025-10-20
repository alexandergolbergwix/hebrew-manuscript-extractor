"""
Entity Classification Module using Grok API
Isolates side effects (API calls) from pure logic
"""

import json
import time
import random
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from tqdm import tqdm

from ..models.entities import ExtractedEntity, ClassifiedEntity, EntityType

# Import Hebrew pattern-based classifier
try:
    from .hebrew_patterns import classify_persons_batch, get_pattern_statistics
    HEBREW_PATTERNS_AVAILABLE = True
except ImportError:
    HEBREW_PATTERNS_AVAILABLE = False
    print("Warning: Hebrew patterns module not available")


# ============================================================================
# ONTOLOGY-AWARE CLASSIFICATION LABELS (Immutable)
# ============================================================================

DATE_LABELS = frozenset([
    # ========== CREATION EVENTS (CIDOC-CRM/LRMoo hierarchy) ==========
    # F27_Work_Creation - Intellectual conception
    "work creation date",
    "work composition date",
    "intellectual creation date",
    
    # F28_Expression_Creation - Specific version/text
    "expression creation date",
    "text creation date",
    "version creation date",
    
    # F30_Manifestation_Creation - Publication/edition
    "manifestation creation date",
    "edition creation date",
    
    # F32_Item_Production_Event / E12_Production - Physical manuscript
    "manuscript production date",
    "copying date",
    "writing date",
    "scribal date",
    
    # ========== PUBLICATION & DISTRIBUTION ==========
    "publication date",
    "printing date",
    "print date",
    "press date",
    
    # ========== MODIFICATION EVENTS (E11_Modification) ==========
    "binding date",
    "restoration date",
    "repair date",
    "modification date",
    "rebinding date",
    "illumination date",
    "decoration date",
    
    # ========== TRANSFER & OWNERSHIP (E10_Transfer_of_Custody, E8_Acquisition) ==========
    "transfer of custody date",
    "acquisition date",
    "purchase date",
    "sale date",
    "donation date",
    "bequest date",
    "gift date",
    "loan date",
    "auction date",
    "confiscation date",
    
    # ========== DOCUMENTATION & SCHOLARLY EVENTS (Reference_Event) ==========
    "cataloging date",
    "reference date",
    "citation date",
    "scholarly reference date",
    "catalog entry date",
    
    # E31_Document events
    "digitization date",
    "imaging date",
    "photographing date",
    "microfilming date",
    
    # Exhibition & display
    "exhibition date",
    "display date",
    
    # ========== PERSON LIFE EVENTS (E67_Birth, E69_Death) ==========
    "birth date",
    "death date",
    "floruit date",
    "active date",
    "marriage date",
    
    # ========== COLOPHON MENTIONS (mentions_date) ==========
    "colophon date",
    "colophon completion date",
    "colophon inscription date",
    
    # ========== ANNOTATIONS & INSCRIPTIONS ==========
    "annotation date",
    "inscription date",
    "marginal note date",
    "gloss date",
    "dedication date",
    "signature date",
    
    # ========== OTHER MANUSCRIPT EVENTS ==========
    "reading date",
    "study date",
    "censorship date",
    "examination date",
])

LOCATION_LABELS = frozenset([
    # ========== PRODUCTION PLACES (P7_took_place_at for E12_Production) ==========
    "production place",
    "written in",
    "copied in",
    "scribed in",
    "created in",
    "produced in",
    
    # Publication places
    "published in",
    "printed in",
    "press location",
    
    # Modification places
    "bound in",
    "restored in",
    "repaired in",
    "illuminated in",
    "decorated in",
    
    # ========== MOVEMENT & TRANSFER (E9_Move, P26/P27) ==========
    "moved to",
    "moved from",
    "transferred to",
    "transferred from",
    "brought from",
    "sent to",
    "dispatched to",
    "shipped from",
    
    # ========== PERSON-PLACE RELATIONS (P74_has_current_or_former_residence) ==========
    # Birth & death (E67_Birth, E69_Death with P7_took_place_at)
    "born in",
    "died in",
    "birth place",
    "death place",
    
    # Residence
    "lived in",
    "resided in",
    "dwelling in",
    "domiciled in",
    
    # Activity places
    "worked in",
    "active in",
    "studied in",
    "taught in",
    
    # ========== CUSTODY & PRESERVATION LOCATIONS ==========
    # Current/historical custody
    "preserved in",
    "kept in",
    "stored in",
    "held in",
    "housed in",
    "located in",
    
    # Ownership location
    "owned in",
    "possession in",
    
    # Repository/institution
    "repository",
    "library location",
    "archive location",
    "collection location",
    
    # NOTE: "colophon place" removed - colophons DESCRIBE events (E12_Production, etc.)
    # Places in colophons should be classified by EVENT type (production, residence, etc.)
    # See: CIDOC-CRM E73_Information_Object (colophon) → P70_documents → Events
    
    # ========== GENERAL MENTIONS (last resort - when no event context) ==========
    "mentioned place",
    "referenced place",
    "cited place",
    "place reference",
    
    # ========== TRAVEL & ACTIVITY ==========
    "visited",
    "traveled to",
    "journeyed to",
    "passed through",
    
    # ========== SCHOLARLY/DOCUMENTATION EVENTS ==========
    "cataloged in",
    "documented in",
    "examined in",
    "photographed in",
    "digitized in",
    
    # ========== EXHIBITION & DISPLAY ==========
    "exhibited in",
    "displayed in",
    "shown in",
])

PERSON_LABELS = frozenset([
    # ========== CORE MANUSCRIPT ROLES (Most Common in Catalog Notes) ==========
    # PRODUCTION ROLES - Physical creation (E12_Production)
    "scribe",                    # סופר - wrote the manuscript (נכתב ביד, על ידי)
    "copyist",                   # מעתיק - copied the text
    "illuminator",               # מאייר - decorated/illustrated (צייר, מאייר)
    
    # INTELLECTUAL ROLES - Work/Expression creation
    "author",                    # מחבר - created work intellectually (מחבר, חיבר)
    "translator",                # מתרגם - translated work
    "commentator",               # מפרש - wrote commentary (פרש, פירש)
    
    # OWNERSHIP & TRANSFER - Custody chain (E10/E8)
    "owner",                     # בעלים - current possessor (רשות, שייך ל)
    "previous owner",            # בעלים קודם - former possessor (היה של)
    "donor",                     # תורם - donated (הקדיש, תרם)
    "purchaser",                 # קונה - bought (קנה, קניתי, רכש)
    "seller",                    # מוכר - sold (מכר, נמכר)
    
    # SCHOLARLY ROLES - Documentation (Reference_Event)
    "cataloger",                 # קטלוג - catalogued manuscript
    "censor",                    # צנזור - censored text
    
    # PATRONAGE & DEDICATION
    "patron",                    # פטרון - commissioned/sponsored
    "dedicatee",                 # נמען - work dedicated to
    
    # COLOPHON-SPECIFIC - mentions_scribe property
    "colophon scribe",           # סופר בקולופון - scribe in colophon
    
    # GENERAL MENTION - Default when no specific role
    "mentioned person",          # אדם נזכר - general mention without role
])


def get_labels_for_entity_type(entity_type: EntityType) -> frozenset:
    """Pure function: Get appropriate labels for entity type"""
    if entity_type == EntityType.DATE:
        return DATE_LABELS
    elif entity_type == EntityType.LOCATION:
        return LOCATION_LABELS
    elif entity_type == EntityType.PERSON:
        return PERSON_LABELS
    else:
        return frozenset()


# ============================================================================
# EVENT/LOCATION ONTOLOGY MAPPINGS (Immutable)
# ============================================================================

EVENT_TYPE_ONTOLOGY_MAPPING = {
    # ========== WORK CREATION (F27_Work_Creation) ==========
    "work creation date": {
        "event_class": "F27_Work_Creation",
        "property": "R16_created",
        "level": "work",
    },
    "work composition date": {
        "event_class": "F27_Work_Creation",
        "property": "R16_created",
        "level": "work",
    },
    "intellectual creation date": {
        "event_class": "F27_Work_Creation",
        "property": "R16_created",
        "level": "work",
    },
    
    # ========== EXPRESSION CREATION (F28_Expression_Creation) ==========
    "expression creation date": {
        "event_class": "F28_Expression_Creation",
        "property": "R17_created",
        "level": "expression",
    },
    "text creation date": {
        "event_class": "F28_Expression_Creation",
        "property": "R17_created",
        "level": "expression",
    },
    "copying date": {
        "event_class": "F28_Expression_Creation",
        "property": "R17_created",
        "level": "expression",
    },
    
    # ========== MANIFESTATION CREATION (F30_Manifestation_Creation) ==========
    "manifestation creation date": {
        "event_class": "F30_Manifestation_Creation",
        "property": "R24_created",
        "level": "manifestation",
    },
    "edition creation date": {
        "event_class": "F30_Manifestation_Creation",
        "property": "R24_created",
        "level": "manifestation",
    },
    
    # ========== MANUSCRIPT PRODUCTION (F32_Item_Production_Event / E12_Production) ==========
    "manuscript production date": {
        "event_class": "F32_Item_Production_Event",
        "crm_class": "E12_Production",
        "property": "R27_materialized",
        "level": "manifestation_singleton",
    },
    "writing date": {
        "event_class": "E12_Production",
        "property": "P108_has_produced",
        "level": "manifestation_singleton",
    },
    "scribal date": {
        "event_class": "E12_Production",
        "property": "P108_has_produced",
        "level": "manifestation_singleton",
    },
    
    # ========== PRINTING & PUBLICATION ==========
    "printing date": {
        "event_class": "F30_Manifestation_Creation",
        "property": "R24_created",
        "level": "manifestation",
    },
    "publication date": {
        "event_class": "F30_Manifestation_Creation",
        "property": "R24_created",
        "level": "manifestation",
    },
    
    # ========== MODIFICATION (E11_Modification) ==========
    "binding date": {
        "event_class": "E11_Modification",
        "property": "P31_has_modified",
    },
    "restoration date": {
        "event_class": "E11_Modification",
        "property": "P31_has_modified",
    },
    "illumination date": {
        "event_class": "E11_Modification",
        "property": "P31_has_modified",
    },
    
    # ========== TRANSFER OF CUSTODY (E10_Transfer_of_Custody) ==========
    "transfer of custody date": {
        "event_class": "E10_Transfer_of_Custody",
        "property": "P30_transferred_custody_of",
    },
    "donation date": {
        "event_class": "E10_Transfer_of_Custody",
        "property": "P30_transferred_custody_of",
    },
    "gift date": {
        "event_class": "E10_Transfer_of_Custody",
        "property": "P30_transferred_custody_of",
    },
    
    # ========== ACQUISITION (E8_Acquisition) ==========
    "acquisition date": {
        "event_class": "E8_Acquisition",
        "property": "P24_transferred_title_of",
    },
    "purchase date": {
        "event_class": "E8_Acquisition",
        "property": "P24_transferred_title_of",
    },
    "sale date": {
        "event_class": "E8_Acquisition",
        "property": "P24_transferred_title_of",
    },
    
    # ========== DOCUMENTATION (Reference_Event, E31_Document) ==========
    "reference date": {
        "event_class": "Reference_Event",
        "property": "P67_refers_to",
    },
    "cataloging date": {
        "event_class": "Reference_Event",
        "property": "P67_refers_to",
    },
    "digitization date": {
        "event_class": "E31_Document",
        "property": "P16_used_specific_object",
    },
    
    # ========== PERSON LIFE EVENTS ==========
    "birth date": {
        "event_class": "E67_Birth",
        "property": "P98_brought_into_life",
    },
    "death date": {
        "event_class": "E69_Death",
        "property": "P100_was_death_of",
    },
    
    # ========== COLOPHON MENTIONS ==========
    "colophon date": {
        "event_class": "Colophon",
        "property": "mentions_date",
    },
    "colophon completion date": {
        "event_class": "Colophon",
        "property": "mentions_date",
    },
    
    # ========== ANNOTATIONS ==========
    "annotation date": {
        "event_class": "E11_Modification",
        "property": "P31_has_modified",
    },
    "inscription date": {
        "event_class": "E11_Modification",
        "property": "P31_has_modified",
    },
}

LOCATION_RELATION_ONTOLOGY_MAPPING = {
    # ========== PRODUCTION PLACES ==========
    "production place": {
        "event_class": "E12_Production",
        "property": "P7_took_place_at",
    },
    "written in": {
        "event_class": "E12_Production",
        "property": "P7_took_place_at",
    },
    "copied in": {
        "event_class": "E12_Production",
        "property": "P7_took_place_at",
    },
    "published in": {
        "event_class": "F30_Manifestation_Creation",
        "property": "P7_took_place_at",
    },
    "printed in": {
        "event_class": "F30_Manifestation_Creation",
        "property": "P7_took_place_at",
    },
    
    # ========== PERSON-PLACE RELATIONS ==========
    "born in": {
        "event_class": "E67_Birth",
        "property": "P7_took_place_at",
    },
    "died in": {
        "event_class": "E69_Death",
        "property": "P7_took_place_at",
    },
    "resided in": {
        "property": "P74_has_current_or_former_residence",
    },
    "lived in": {
        "property": "P74_has_current_or_former_residence",
    },
    
    # ========== MOVEMENT ==========
    "moved to": {
        "event_class": "E9_Move",
        "property": "P26_moved_to",
    },
    "moved from": {
        "event_class": "E9_Move",
        "property": "P27_moved_from",
    },
    "sent to": {
        "event_class": "E10_Transfer_of_Custody",
        "property": "P26_moved_to",
    },
    
    # NOTE: "colophon place" mapping removed - colophons describe events
    # Places mentioned in colophons should map to the appropriate event type
    # (production, residence, etc.) not a generic "colophon place"
    
    # ========== GENERAL MENTIONS (last resort when no event identified) ==========
    "mentioned place": {
        "property": "mentions_place",
    },
    "preserved in": {
        "property": "P55_has_current_location",
    },
}

PERSON_ROLE_ONTOLOGY_MAPPING = {
    # ========== PRODUCTION ROLES (E12_Production) ==========
    "scribe": {
        "property": "has_scribe",
        "event_role": "P14_carried_out_by",
        "event_class": "E12_Production",
    },
    "copyist": {
        "property": "has_scribe",
        "event_role": "P14_carried_out_by",
        "event_class": "F28_Expression_Creation",
    },
    "illuminator": {
        "property": "has_illuminator",
        "event_role": "P14_carried_out_by",
        "event_class": "E11_Modification",
    },
    
    # ========== INTELLECTUAL CREATION (F27/F28) ==========
    "author": {
        "property": "has_author",
        "event_role": "P14_carried_out_by",
        "event_class": "F27_Work_Creation",
    },
    "translator": {
        "property": "has_translator",
        "event_role": "P14_carried_out_by",
        "event_class": "F28_Expression_Creation",
    },
    "commentator": {
        "property": "has_commentator",
        "event_role": "P14_carried_out_by",
        "event_class": "F28_Expression_Creation",
    },
    
    # ========== OWNERSHIP & TRANSFER (E10/E8) ==========
    "owner": {
        "property": "has_owner",
        "event_role": "P29_custody_received_by",
        "event_class": "E10_Transfer_of_Custody",
    },
    "previous owner": {
        "property": "has_previous_owner",
        "event_role": "P28_custody_surrendered_by",
        "event_class": "E10_Transfer_of_Custody",
    },
    "donor": {
        "property": "has_donor",
        "event_role": "P28_custody_surrendered_by",
        "event_class": "E10_Transfer_of_Custody",
    },
    "purchaser": {
        "property": "has_purchaser",
        "event_role": "P22_acquired_title_to",
        "event_class": "E8_Acquisition",
    },
    "seller": {
        "property": "has_seller",
        "event_role": "P23_transferred_title_from",
        "event_class": "E8_Acquisition",
    },
    
    # ========== SCHOLARLY & DOCUMENTATION (Reference_Event) ==========
    "cataloger": {
        "property": "has_cataloger",
        "event_role": "P14_carried_out_by",
        "event_class": "Reference_Event",
    },
    "censor": {
        "property": "has_censor",
        "event_role": "P14_carried_out_by",
        "event_class": "E7_Activity",
    },
    
    # ========== PATRONAGE ==========
    "patron": {
        "property": "has_patron",
        "event_role": "P14_carried_out_by",
        "event_class": "E7_Activity",
    },
    "dedicatee": {
        "property": "has_dedicatee",
        "event_role": None,
        "event_class": None,
    },
    
    # ========== COLOPHON-SPECIFIC ==========
    "colophon scribe": {
        "property": "mentions_scribe",
        "context": "Colophon",
        "event_role": "P14_carried_out_by",
        "event_class": "E12_Production",
    },
    
    # ========== GENERAL MENTION ==========
    "mentioned person": {
        "property": "mentions_person",
        "event_role": None,
        "event_class": None,
    },
}


@lru_cache(maxsize=100)
def get_ontology_mapping(label: str) -> Dict[str, str]:
    """Pure function: Get ontology mapping for classification label"""
    return (EVENT_TYPE_ONTOLOGY_MAPPING.get(label) or 
            LOCATION_RELATION_ONTOLOGY_MAPPING.get(label) or 
            PERSON_ROLE_ONTOLOGY_MAPPING.get(label) or
            {"event_class": "E7_Activity"})


# ============================================================================
# GROK API CLIENT - Side Effects Isolated
# ============================================================================

class GrokClassifier:
    """
    Handles Grok API calls - isolated from pure logic
    Follows functional principles where possible
    """
    
    def __init__(
        self,
        api_key: str,
        max_workers: int = 8,
        chunk_size: int = 8,
        retries: int = 3,
        timeout: int = 35
    ):
        self.api_key = api_key
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.retries = retries
        self.timeout = timeout
        self.api_url = "https://api.x.ai/v1/chat/completions"
    
    def classify_entities(
        self,
        text: str,
        entities: List[ExtractedEntity]
    ) -> List[ClassifiedEntity]:
        """
        Classify entities using Grok API
        
        Args:
            text: Source text context
            entities: List of extracted entities
            
        Returns:
            List of classified entities with labels
        """
        if not entities:
            return []
        
        # Group by entity type
        entities_by_type = self._group_by_type(entities)
        
        all_classified = []
        
        for entity_type, type_entities in entities_by_type.items():
            classified = self._classify_batch(
                text=text,
                entities=type_entities,
                entity_type=entity_type
            )
            all_classified.extend(classified)
        
        return all_classified
    
    def _group_by_type(
        self,
        entities: List[ExtractedEntity]
    ) -> Dict[EntityType, List[ExtractedEntity]]:
        """Pure function: Group entities by type"""
        groups: Dict[EntityType, List[ExtractedEntity]] = {}
        for entity in entities:
            if entity.entity_type not in groups:
                groups[entity.entity_type] = []
            groups[entity.entity_type].append(entity)
        return groups
    
    def _classify_batch(
        self,
        text: str,
        entities: List[ExtractedEntity],
        entity_type: EntityType
    ) -> List[ClassifiedEntity]:
        """
        Classify batch of entities of same type
        HYBRID APPROACH: Hebrew patterns FIRST → Grok API fallback
        """
        
        # Get appropriate labels
        labels = list(get_labels_for_entity_type(entity_type))
        
        # Deduplicate entity values
        unique_values = list({e.value for e in entities})
        
        # Create entity lookup
        entity_map = {e.value: e for e in entities}
        
        # ========== STEP 1: Try Hebrew Patterns (for PERSONS only) ==========
        pattern_results = {}
        unclassified_values = unique_values
        
        if entity_type == EntityType.PERSON and HEBREW_PATTERNS_AVAILABLE:
            print(f"    🔍 Regex patterns: Checking {len(unique_values)} persons...")
            pattern_results = classify_persons_batch(text, unique_values)
            
            # Count successes
            classified_by_pattern = sum(1 for v in pattern_results.values() if v)
            unclassified_values = [v for v, role in pattern_results.items() if not role]
            
            print(f"    ✅ Regex classified: {classified_by_pattern}/{len(unique_values)}")
            print(f"    ⏩ Grok fallback needed: {len(unclassified_values)}")
        
        # ========== STEP 2: Grok API for remaining entities ==========
        all_results = dict(pattern_results)  # Start with pattern results
        
        if unclassified_values:
            # Split into chunks
            chunks = self._create_chunks(unclassified_values, self.chunk_size)
            
            # Parallel API calls with progress tracking
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(
                        self._classify_chunk,
                        text, chunk, entity_type.value, labels
                    )
                    for chunk in chunks
                ]
                
                # Progress bar for API calls
                for future in tqdm(
                    as_completed(futures), 
                    total=len(futures), 
                    desc=f"  API calls ({entity_type.value})", 
                    unit="batch",
                    leave=False
                ):
                    try:
                        result = future.result()
                        all_results.update(result)  # Merge Grok results
                    except Exception as e:
                        print(f"\nClassification error: {e}")
        
        # ========== STEP 3: Build classified entities ==========
        classified = []
        for value, label in all_results.items():
            if label and value in entity_map:  # Only if classified
                ontology_mapping = get_ontology_mapping(label)
                classified_entity = ClassifiedEntity(
                    entity=entity_map[value],
                    label=label,
                    ontology_mapping=ontology_mapping
                )
                classified.append(classified_entity)
        
        return classified
    
    def _classify_chunk(
        self,
        text: str,
        items: List[str],
        item_kind: str,
        labels: List[str]
    ) -> Dict[str, str]:
        """Make API call for one chunk - isolated side effect"""
        
        try:
            import requests
        except ImportError:
            print("Warning: requests library not available")
            return {}
        
        prompt = {
            "text": text[:4000],
            "items": items,
            "item_kind": item_kind,
            "labels": labels,
            "instruction": self._get_instruction(item_kind)
        }
        
        for attempt in range(self.retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "messages": [
                            {
                                "role": "system",
                                "content": self._get_system_prompt()
                            },
                            {
                                "role": "user",
                                "content": json.dumps(prompt, ensure_ascii=False)
                            }
                        ],
                        "model": "grok-4-fast-non-reasoning",
                        "stream": False,
                        "temperature": 0.0,
                    },
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                mapping = json.loads(content)
                
                # Validate results
                if isinstance(mapping, dict):
                    return {k: v for k, v in mapping.items() 
                           if v in labels}
                
            except Exception as e:
                if attempt == self.retries - 1:
                    print(f"API call failed after {self.retries} attempts: {e}")
                else:
                    sleep_time = min(30.0, (2 ** attempt) + random.random())
                    time.sleep(sleep_time)
        
        return {}
    
    @staticmethod
    def _get_system_prompt() -> str:
        """Pure function: Get system prompt for Grok"""
        return (
            "You are a Hebrew manuscript expert. Classify entities by their ROLE using Hebrew context clues.\n"
            "Return ONLY valid JSON: {\"entity\": \"label\", ...}\n\n"
            
            "========== ONTOLOGY LEVELS (CIDOC-CRM/LRMoo) ==========\n"
            "1. F1 WORK - Intellectual conception (e.g., 'Ginat Egoz' as abstract work)\n"
            "2. F2 EXPRESSION - Specific text version (e.g., Hebrew translation vs. original)\n"
            "3. F4 MANIFESTATION SINGLETON - Physical manuscript (unique copy)\n\n"
            
            "========== DATE CLASSIFICATION RULES ==========\n"
            "• WORK creation: Original intellectual composition (author's lifetime)\n"
            "• EXPRESSION creation: Translation, commentary, version creation\n"
            "• MANUSCRIPT production: Physical copying (scribe's work) - נכתב, הועתק, נשלם\n"
            "• PRINTING: Press publication - נדפס\n"
            "• SALE/TRANSFER: Ownership change - נמכר, נרכש, נמסר, קנה\n"
            "• COLOPHON date: Explicitly in colophon text - קולופון, נשלם ספר\n"
            "• ANNOTATION: Added notes - הערה, רשם, הוסיף\n"
            "• PERSON dates: Birth/death - נולד, נפטר, מת\n\n"
            
            "========== LOCATION CLASSIFICATION (EVENT-BASED per CIDOC-CRM) ==========\n"
            "Locations are classified by their RELATIONSHIP to EVENTS, not by where they're mentioned!\n"
            "A colophon DESCRIBES events - classify by EVENT TYPE, not 'colophon place':\n\n"
            "• PRODUCTION place (E12_Production → P7_took_place_at):\n"
            "  Where manuscript physically created - נכתב ב, הועתק ב, נשלם ב, נעשה ב\n"
            "  Examples: 'נשלם בקנדיה' → production place (Candia)\n\n"
            "• PUBLISHED in (F30_Manifestation_Creation → P7_took_place_at):\n"
            "  Press/print location - נדפס ב, הודפס ב, דפוס\n\n"
            "• RESIDED in (P74_has_current_or_former_residence):\n"
            "  Person's dwelling - גר ב, ישב ב, דר ב, מושבו ב\n\n"
            "• BORN in (E67_Birth → P7_took_place_at): נולד ב, יליד\n"
            "• DIED in (E69_Death → P7_took_place_at): נפטר ב, מת ב\n"
            "• WORKED in (E7_Activity → P7_took_place_at): פעל ב, עבד ב\n\n"
            "• PRESERVED in (P55_has_current_location):\n"
            "  Current repository - נמצא ב, שמור ב, ספריית, באוסף\n\n"
            "• TRANSFERRED to (E10_Transfer_of_Custody): הועבר ל, נמכר ל\n\n"
            "• MENTIONED place: LAST RESORT - only if no event relationship identified\n\n"
            
            "========== PERSON CLASSIFICATION (Fallback for Ambiguous Cases) ==========\n"
            "NOTE: You are classifying ONLY ambiguous persons that regex patterns couldn't identify.\n"
            "These are persons WITHOUT clear Hebrew markers. Use CONTEXT CLUES:\n\n"
            
            "- Look at WHOLE SENTENCE context (not just adjacent words)\n"
            "- Consider person's POSITION in text (title, colophon, ownership note?)\n"
            "- Check for IMPLICIT roles (e.g., 'בן' often indicates family, not role)\n"
            "- Identify QUOTED sources (may be authors of other works)\n"
            "- Note FAMILY RELATIONS (father/son in name → may be identifier, not role)\n\n"
            
            "CONSERVATIVE APPROACH:\n"
            "If role is UNCLEAR → use 'mentioned person'\n"
            "Only assign specific role if CONFIDENT from context\n\n"
            
            "========== INSTRUCTIONS ==========\n"
            "1. Read the Hebrew text carefully\n"
            "2. For each entity, look for Hebrew marker words nearby\n"
            "3. Match marker to label from the list provided\n"
            "4. If no marker found: use default (unclassified/mentioned person)\n"
            "5. Return valid JSON mapping: {\"entity\": \"label\"}\n\n"
            
            "BE PRECISE: Use the exact label text from the provided list."
        )
    
    @staticmethod
    def _get_instruction(item_kind: str) -> str:
        """Pure function: Get instruction text for classification"""
        return (
            f"Classify each {item_kind} using Hebrew context clues from the text. "
            f"Match to ONE label from 'labels' list. "
            f"Return JSON: {{\"item\": \"label\"}}"
        )
    
    @staticmethod
    def _create_chunks(items: List[str], chunk_size: int) -> List[List[str]]:
        """Pure function: Split list into chunks"""
        return [items[i:i + chunk_size] 
                for i in range(0, len(items), chunk_size)]


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_classifier(config) -> Optional[GrokClassifier]:
    """
    Factory function to create classifier if enabled
    
    Args:
        config: Application configuration object
        
    Returns:
        GrokClassifier instance or None
    """
    if not config.use_grok or not config.grok_api_key:
        return None
    
    return GrokClassifier(
        api_key=config.grok_api_key,
        max_workers=config.grok_max_workers,
        chunk_size=config.grok_chunk_size,
        retries=config.grok_retries,
        timeout=config.grok_timeout
    )
