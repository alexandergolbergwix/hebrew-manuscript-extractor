"""
Domain Models - Immutable Data Structures
Following functional programming principles with dataclasses
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class EntityType(Enum):
    """Types of extracted entities"""
    DATE = "date"
    LOCATION = "location"
    PERSON = "person"
    WORK = "work"
    ORGANIZATION = "organization"


class EventClass(Enum):
    """CIDOC-CRM Event Classes"""
    E12_PRODUCTION = "E12_Production"
    E10_TRANSFER_OF_CUSTODY = "E10_Transfer_of_Custody"
    E8_ACQUISITION = "E8_Acquisition"
    E11_MODIFICATION = "E11_Modification"
    E67_BIRTH = "E67_Birth"
    E69_DEATH = "E69_Death"
    E7_ACTIVITY = "E7_Activity"
    F32_ITEM_PRODUCTION = "F32_Item_Production_Event"
    F28_EXPRESSION_CREATION = "F28_Expression_Creation"
    REFERENCE_EVENT = "Reference_Event"


@dataclass(frozen=True)
class ExtractedEntity:
    """Immutable representation of an extracted entity"""
    value: str
    entity_type: EntityType
    confidence: float = 1.0
    context: str = ""
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None
    metadata: Optional[Dict] = None  # Additional metadata (e.g., Wikidata, coordinates)
    
    def __post_init__(self):
        """Validate entity data"""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if not self.value.strip():
            raise ValueError("Entity value cannot be empty")


@dataclass(frozen=True)
class ClassifiedEntity:
    """Entity with classification label"""
    entity: ExtractedEntity
    label: str
    ontology_mapping: Dict[str, str] = field(default_factory=dict)
    
    @property
    def value(self) -> str:
        return self.entity.value
    
    @property
    def entity_type(self) -> EntityType:
        return self.entity.entity_type


@dataclass(frozen=True)
class ColophonInfo:
    """Structured colophon information"""
    text: str
    has_completion_marker: bool
    scribe_name: Optional[str] = None
    date_mentioned: Optional[str] = None
    place_mentioned: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        return bool(self.text.strip())


@dataclass(frozen=True)
class Person:
    """Representation of a person (scribe, author, etc.)"""
    name: str
    patronymic: Optional[str] = None
    role: Optional[str] = None  # "scribe", "author", etc.
    nli_uri: Optional[str] = None
    wikidata_uri: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        if self.patronymic:
            return f"{self.name} בן {self.patronymic}"
        return self.name


@dataclass(frozen=True)
class Place:
    """Representation of a geographic location"""
    name: str
    modern_name: Optional[str] = None
    nli_uri: Optional[str] = None
    geonames_uri: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None


@dataclass(frozen=True)
class Work:
    """Representation of an intellectual work (F1_Work)"""
    title: str
    author: Optional[Person] = None
    language: str = "Hebrew"
    subject: Optional[str] = None


@dataclass(frozen=True)
class Expression:
    """Specific version of a work (F2_Expression)"""
    work: Work
    manuscript_id: str
    language: str = "Hebrew"


@dataclass(frozen=True)
class Event:
    """Structured event following CIDOC-CRM"""
    event_type: str
    event_class: EventClass
    manuscript_id: str
    date: Optional[str] = None
    place: Optional[Place] = None
    actor: Optional[Person] = None
    properties: Dict[str, str] = field(default_factory=dict)
    
    @property
    def has_temporal_info(self) -> bool:
        return self.date is not None
    
    @property
    def has_spatial_info(self) -> bool:
        return self.place is not None


@dataclass(frozen=True)
class Manuscript:
    """Complete manuscript record (F4_Manifestation_Singleton)"""
    manuscript_id: str
    notes_text: str
    
    # Extracted information
    dates: List[ExtractedEntity] = field(default_factory=list)
    locations: List[ExtractedEntity] = field(default_factory=list)
    persons: List[Person] = field(default_factory=list)
    
    # Structured information
    colophon: Optional[ColophonInfo] = None
    work: Optional[Work] = None
    expression: Optional[Expression] = None
    events: List[Event] = field(default_factory=list)
    
    # Authority enrichment
    nli_uri: Optional[str] = None
    
    # Source metadata (pass-through from input)
    source_metadata: Dict[str, str] = field(default_factory=dict)
    
    @property
    def has_colophon(self) -> bool:
        return self.colophon is not None and self.colophon.is_valid
    
    @property
    def primary_scribe(self) -> Optional[Person]:
        """Get the primary scribe if identified"""
        if self.colophon and self.colophon.scribe_name:
            return next((p for p in self.persons if p.role == "scribe"), None)
        return None
    
    @property
    def production_events(self) -> List[Event]:
        """Filter production-related events"""
        return [e for e in self.events 
                if e.event_class in (EventClass.E12_PRODUCTION, EventClass.F32_ITEM_PRODUCTION)]


@dataclass(frozen=True)
class ExtractionResult:
    """Complete extraction results for processing pipeline"""
    manuscripts: List[Manuscript]
    extraction_date: datetime
    total_dates_extracted: int
    total_locations_extracted: int
    total_persons_extracted: int
    total_events_created: int
    
    @property
    def summary(self) -> Dict[str, int]:
        return {
            "manuscripts": len(self.manuscripts),
            "dates": self.total_dates_extracted,
            "locations": self.total_locations_extracted,
            "persons": self.total_persons_extracted,
            "events": self.total_events_created,
            "colophons": sum(1 for m in self.manuscripts if m.has_colophon),
        }


@dataclass(frozen=True)
class Config:
    """Application configuration - immutable"""
    # Paths
    input_excel_path: str
    output_dir: str
    gazetteer_path: Optional[str] = None
    
    # Behavior
    min_token_length: int = 2
    max_location_tokens: int = 6
    use_grok: bool = True
    ai_only: bool = False  # Use AI for extraction instead of regex patterns
    use_kima: bool = False  # Use Kima/Maagarim gazetteer for locations
    
    # API
    grok_api_key: Optional[str] = None
    grok_max_workers: int = 8
    grok_chunk_size: int = 8
    grok_retries: int = 3
    grok_timeout: int = 35
    
    # Ontology namespaces
    base_namespace: str = "http://data.hebrewmanuscripts.org/"
    hm_namespace: str = "http://www.ontology.org.il/HebrewManuscripts/2025-08-19#"
    crm_namespace: str = "http://www.cidoc-crm.org/cidoc-crm/"
    lrmoo_namespace: str = "http://iflastandards.info/ns/lrm/lrmoo/"
    
    def validate(self) -> bool:
        """Validate configuration"""
        import os
        if not os.path.exists(self.input_excel_path):
            raise ValueError(f"Input file not found: {self.input_excel_path}")
        if self.use_grok and not self.grok_api_key:
            raise ValueError("Grok API key required when use_grok=True")
        if self.ai_only and not self.grok_api_key:
            raise ValueError("Grok API key required when ai_only=True")
        return True
