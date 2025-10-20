"""
RDF Knowledge Graph Generation Module
Pure transformations: Data → RDF Triples
Following CIDOC-CRM and LRMoo ontology standards
"""

from typing import Optional, Tuple
from functools import lru_cache
from urllib.parse import quote

try:
    from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD
    from rdflib.namespace import DCTERMS, SKOS
    RDF_AVAILABLE = True
except ImportError:
    RDF_AVAILABLE = False
    print("Warning: rdflib not available. Install with: pip install rdflib")

from ..models.entities import (
    Manuscript, Event, Person, Place, Work, Expression,
    ColophonInfo, ClassifiedEntity, EventClass
)


# ============================================================================
# ONTOLOGY NAMESPACES (Immutable)
# ============================================================================

class OntologyNamespaces:
    """Immutable namespace configuration"""
    
    def __init__(self, config):
        if not RDF_AVAILABLE:
            return
            
        self.BASE = Namespace(config.base_namespace)
        self.HM = Namespace(config.hm_namespace)
        self.CRM = Namespace(config.crm_namespace)
        self.LRMOO = Namespace(config.lrmoo_namespace)
        self.NLI = Namespace("http://nli.org.il/he/authorities/")
        self.WD = Namespace("http://www.wikidata.org/entity/")
    
    def bind_to_graph(self, graph: 'Graph') -> None:
        """Bind namespaces to RDF graph"""
        if not RDF_AVAILABLE:
            return
            
        graph.bind("base", self.BASE)
        graph.bind("hm", self.HM)
        graph.bind("crm", self.CRM)
        graph.bind("lrmoo", self.LRMOO)
        graph.bind("nli", self.NLI)
        graph.bind("dcterms", DCTERMS)


# ============================================================================
# URI GENERATION - Pure Functions
# ============================================================================

def normalize_for_uri(text: str) -> str:
    """Pure function: Normalize text for URI component with URL encoding"""
    # First do basic normalization
    normalized = text.strip().replace(" ", "_").replace("בן", "ben").replace('"', '').replace("'", '')
    # Then URL-encode to handle Hebrew and other non-ASCII characters
    # safe='_' keeps underscores unencoded
    return quote(normalized, safe='_')


@lru_cache(maxsize=1000)
def create_manuscript_uri(base: str, manuscript_id: str) -> str:
    """Pure function: Create URI for manuscript"""
    clean_id = normalize_for_uri(manuscript_id)
    return f"{base}MS_{clean_id}"


@lru_cache(maxsize=1000)
def create_event_uri(base: str, manuscript_id: str, event_type: str, index: int = 0) -> str:
    """Pure function: Create URI for event"""
    clean_id = normalize_for_uri(manuscript_id)
    clean_type = event_type.replace(" ", "_").replace("_date", "")
    suffix = f"_{index}" if index > 0 else ""
    return f"{base}MS_{clean_id}_{clean_type}_Event{suffix}"


@lru_cache(maxsize=1000)
def create_person_uri(base: str, person_name: str) -> str:
    """Pure function: Create URI for person"""
    clean_name = normalize_for_uri(person_name)
    return f"{base}Person_{clean_name}"


@lru_cache(maxsize=1000)
def create_place_uri(base: str, place_name: str) -> str:
    """Pure function: Create URI for place"""
    clean_name = normalize_for_uri(place_name)
    return f"{base}Place_{clean_name}"


@lru_cache(maxsize=1000)
def create_timespan_uri(base: str, date_value: str) -> str:
    """Pure function: Create URI for timespan"""
    # Normalize and URL-encode to handle Hebrew dates and special characters
    clean_date = normalize_for_uri(date_value.replace("-", "_"))
    return f"{base}TimeSpan_{clean_date}"


@lru_cache(maxsize=1000)
def create_work_uri(base: str, work_title: str) -> str:
    """Pure function: Create URI for work"""
    clean_title = normalize_for_uri(work_title)
    return f"{base}Work_{clean_title}"


def create_expression_uri(base: str, work_title: str, manuscript_id: str) -> str:
    """Pure function: Create URI for expression"""
    clean_title = normalize_for_uri(work_title)
    clean_id = normalize_for_uri(manuscript_id)
    return f"{base}Expression_{clean_title}_MS_{clean_id}"


# ============================================================================
# RDF GRAPH BUILDER - Functional Approach
# ============================================================================

class RDFGraphBuilder:
    """
    Builds RDF graphs using functional composition
    State is encapsulated, operations are pure transformations
    """
    
    def __init__(self, config):
        if not RDF_AVAILABLE:
            raise ImportError("rdflib is required for RDF generation")
        
        self.graph = Graph()
        self.ns = OntologyNamespaces(config)
        self.ns.bind_to_graph(self.graph)
        self.base_uri = config.base_namespace
    
    def add_manuscript(self, manuscript: Manuscript) -> URIRef:
        """Add manuscript as F4_Manifestation_Singleton"""
        ms_uri = URIRef(create_manuscript_uri(self.base_uri, manuscript.manuscript_id))
        
        # Type assertions
        self.graph.add((ms_uri, RDF.type, self.ns.LRMOO.F4_Manifestation_Singleton))
        self.graph.add((ms_uri, RDF.type, self.ns.HM.Codicological_Unit))
        
        # Identifier
        self.graph.add((ms_uri, self.ns.CRM.P1_is_identified_by, 
                       Literal(manuscript.manuscript_id, datatype=XSD.string)))
        
        # Labels
        self.graph.add((ms_uri, RDFS.label, 
                       Literal(f"Manuscript {manuscript.manuscript_id}", lang="en")))
        self.graph.add((ms_uri, RDFS.label, 
                       Literal(f"כתב יד {manuscript.manuscript_id}", lang="he")))
        
        # Add NLI URI if present
        if manuscript.nli_uri:
            self.graph.add((ms_uri, self.ns.HM.external_uri_nli, 
                           URIRef(manuscript.nli_uri)))
        
        return ms_uri
    
    def add_person(self, person: Person) -> URIRef:
        """Add person as E21_Person"""
        person_uri = URIRef(create_person_uri(self.base_uri, person.full_name))
        
        self.graph.add((person_uri, RDF.type, self.ns.CRM.E21_Person))
        self.graph.add((person_uri, RDFS.label, 
                       Literal(person.full_name, lang="he")))
        
        # Add role if specified
        if person.role:
            self.graph.add((person_uri, self.ns.HM.has_role, 
                           Literal(person.role, lang="en")))
        
        # Add external URIs
        if person.nli_uri:
            self.graph.add((person_uri, self.ns.HM.external_uri_nli, 
                           URIRef(person.nli_uri)))
        if person.wikidata_uri:
            self.graph.add((person_uri, self.ns.HM.external_uri_wikidata, 
                           URIRef(person.wikidata_uri)))
        
        return person_uri
    
    def add_place(self, place: Place) -> URIRef:
        """Add place as E53_Place"""
        place_uri = URIRef(create_place_uri(self.base_uri, place.name))
        
        self.graph.add((place_uri, RDF.type, self.ns.CRM.E53_Place))
        self.graph.add((place_uri, RDFS.label, Literal(place.name, lang="he")))
        
        if place.modern_name:
            self.graph.add((place_uri, self.ns.HM.modern_name, 
                           Literal(place.modern_name, lang="en")))
        
        # Add external URIs
        if place.nli_uri:
            self.graph.add((place_uri, self.ns.HM.external_uri_nli, 
                           URIRef(place.nli_uri)))
        if place.geonames_uri:
            self.graph.add((place_uri, self.ns.HM.external_uri_geonames, 
                           URIRef(place.geonames_uri)))
        
        # Add coordinates if present
        if place.coordinates:
            lat, lon = place.coordinates
            self.graph.add((place_uri, self.ns.HM.latitude, 
                           Literal(lat, datatype=XSD.decimal)))
            self.graph.add((place_uri, self.ns.HM.longitude, 
                           Literal(lon, datatype=XSD.decimal)))
        
        return place_uri
    
    def add_production_event(
        self,
        manuscript_uri: URIRef,
        manuscript: Manuscript,
        date: Optional[str] = None,
        place: Optional[Place] = None,
        scribe: Optional[Person] = None
    ) -> URIRef:
        """Add E12_Production event"""
        event_uri = URIRef(create_event_uri(
            self.base_uri, 
            manuscript.manuscript_id, 
            "Production"
        ))
        
        # Event types
        self.graph.add((event_uri, RDF.type, self.ns.CRM.E12_Production))
        self.graph.add((event_uri, RDF.type, self.ns.LRMOO.F32_Item_Production_Event))
        
        # Link to manuscript
        self.graph.add((event_uri, self.ns.LRMOO.R27_materialized, manuscript_uri))
        
        # Add temporal info
        if date:
            timespan_uri = URIRef(create_timespan_uri(self.base_uri, date))
            self.graph.add((timespan_uri, RDF.type, self.ns.CRM.E52_Time_Span))
            self.graph.add((timespan_uri, RDFS.label, Literal(date)))
            self.graph.add((event_uri, self.ns.CRM.P4_has_time_span, timespan_uri))
        
        # Add spatial info
        if place:
            place_uri = self.add_place(place)
            self.graph.add((event_uri, self.ns.CRM.P7_took_place_at, place_uri))
        
        # Add actor (scribe)
        if scribe:
            scribe_uri = self.add_person(scribe)
            self.graph.add((event_uri, self.ns.CRM.P14_carried_out_by, scribe_uri))
            self.graph.add((manuscript_uri, self.ns.HM.has_scribe, scribe_uri))
        
        # Label
        self.graph.add((event_uri, RDFS.label, 
                       Literal(f"Production of MS {manuscript.manuscript_id}", lang="en")))
        
        return event_uri
    
    def add_colophon(
        self,
        manuscript_uri: URIRef,
        manuscript: Manuscript,
        colophon: ColophonInfo
    ) -> URIRef:
        """Add colophon as E73_Information_Object"""
        clean_id = normalize_for_uri(manuscript.manuscript_id)
        colophon_uri = URIRef(f"{self.base_uri}MS_{clean_id}_Colophon")
        
        # Types
        self.graph.add((colophon_uri, RDF.type, self.ns.HM.Colophon))
        self.graph.add((colophon_uri, RDF.type, self.ns.CRM.E73_Information_Object))
        
        # Link to manuscript
        self.graph.add((manuscript_uri, self.ns.HM.has_colophon, colophon_uri))
        
        # Add text
        self.graph.add((colophon_uri, self.ns.HM.colophon_text, 
                       Literal(colophon.text, lang="he")))
        
        # Link to scribe if mentioned
        if colophon.scribe_name:
            scribe_uri = URIRef(create_person_uri(self.base_uri, colophon.scribe_name))
            self.graph.add((colophon_uri, self.ns.HM.mentions_scribe, scribe_uri))
        
        return colophon_uri
    
    def add_work_expression_manifestation(
        self,
        manuscript_uri: URIRef,
        manuscript: Manuscript,
        work: Work
    ) -> Tuple[URIRef, URIRef]:
        """Create Work → Expression → Manifestation hierarchy"""
        
        # Create Work (F1_Work)
        work_uri = URIRef(create_work_uri(self.base_uri, work.title))
        self.graph.add((work_uri, RDF.type, self.ns.LRMOO.F1_Work))
        self.graph.add((work_uri, RDFS.label, Literal(work.title, lang="he")))
        self.graph.add((work_uri, self.ns.HM.has_title, Literal(work.title, lang="he")))
        
        # Link author
        if work.author:
            author_uri = self.add_person(work.author)
            self.graph.add((work_uri, self.ns.HM.has_author, author_uri))
        
        # Create Expression (F2_Expression)
        expression_uri = URIRef(create_expression_uri(
            self.base_uri, 
            work.title, 
            manuscript.manuscript_id
        ))
        
        self.graph.add((expression_uri, RDF.type, self.ns.LRMOO.F2_Expression))
        self.graph.add((expression_uri, self.ns.LRMOO.R3_is_realised_in, work_uri))
        self.graph.add((expression_uri, RDFS.label, 
                       Literal(f"{work.title} - Expression in MS {manuscript.manuscript_id}", lang="en")))
        
        # Add language
        if work.language == "Hebrew":
            self.graph.add((expression_uri, self.ns.CRM.P72_has_language, self.ns.HM.Hebrew))
        
        # Link Expression to Manifestation
        self.graph.add((manuscript_uri, self.ns.LRMOO.R4_embodies, expression_uri))
        
        return work_uri, expression_uri
    
    def add_classified_entity_relation(
        self,
        manuscript_uri: URIRef,
        manuscript_id: str,
        classified_entity: ClassifiedEntity
    ) -> Optional[URIRef]:
        """
        Add classified entity with its specific ontological relationship
        
        Args:
            manuscript_uri: URI of the manuscript
            manuscript_id: Manuscript identifier
            classified_entity: Entity with classification label and ontology mapping
            
        Returns:
            URI of created event/entity or None
        """
        from ..models.entities import EntityType
        
        # Get ontology mapping
        mapping = classified_entity.ontology_mapping
        if not mapping:
            return None
        
        # Handle person relationships
        if classified_entity.entity_type == EntityType.PERSON:
            person = Person(name=classified_entity.value, role=classified_entity.label)
            person_uri = self.add_person(person)
            
            # Add direct property if specified
            if "property" in mapping:
                property_name = mapping["property"]
                self.graph.add((manuscript_uri, self.ns.HM[property_name], person_uri))
            
            # Create event if specified
            if mapping.get("event_class"):
                event_uri = URIRef(create_event_uri(
                    self.base_uri,
                    manuscript_id,
                    classified_entity.label.replace(" ", "_"),
                    0
                ))
                
                event_class = mapping["event_class"]
                if event_class.startswith("F"):
                    self.graph.add((event_uri, RDF.type, self.ns.LRMOO[event_class]))
                else:
                    self.graph.add((event_uri, RDF.type, self.ns.CRM[event_class]))
                
                # Link person to event
                if mapping.get("event_role"):
                    self.graph.add((event_uri, self.ns.CRM[mapping["event_role"]], person_uri))
                
                return event_uri
            
            return person_uri
        
        # Handle location relationships
        elif classified_entity.entity_type == EntityType.LOCATION:
            place = Place(name=classified_entity.value)
            place_uri = self.add_place(place)
            
            # Create event if specified
            if mapping.get("event_class"):
                event_uri = URIRef(create_event_uri(
                    self.base_uri,
                    manuscript_id,
                    classified_entity.label.replace(" ", "_"),
                    0
                ))
                
                event_class = mapping["event_class"]
                if event_class.startswith("F"):
                    self.graph.add((event_uri, RDF.type, self.ns.LRMOO[event_class]))
                else:
                    self.graph.add((event_uri, RDF.type, self.ns.CRM[event_class]))
                
                # Link place to event
                if mapping.get("place_property"):
                    self.graph.add((event_uri, self.ns.CRM[mapping["place_property"]], place_uri))
                
                return event_uri
            
            return place_uri
        
        # Handle date relationships
        elif classified_entity.entity_type == EntityType.DATE:
            timespan_uri = URIRef(create_timespan_uri(self.base_uri, classified_entity.value))
            self.graph.add((timespan_uri, RDF.type, self.ns.CRM.E52_Time_Span))
            self.graph.add((timespan_uri, RDFS.label, Literal(classified_entity.value)))
            
            # Create event if specified
            if mapping.get("event_class"):
                event_uri = URIRef(create_event_uri(
                    self.base_uri,
                    manuscript_id,
                    classified_entity.label.replace(" ", "_"),
                    0
                ))
                
                event_class = mapping["event_class"]
                if event_class.startswith("F"):
                    self.graph.add((event_uri, RDF.type, self.ns.LRMOO[event_class]))
                else:
                    self.graph.add((event_uri, RDF.type, self.ns.CRM[event_class]))
                
                # Link timespan to event
                self.graph.add((event_uri, self.ns.CRM.P4_has_time_span, timespan_uri))
                
                # Link event to manuscript
                if mapping.get("property_to_manuscript"):
                    prop = mapping["property_to_manuscript"]
                    if prop.startswith("R"):
                        self.graph.add((event_uri, self.ns.LRMOO[prop], manuscript_uri))
                    else:
                        self.graph.add((event_uri, self.ns.CRM[prop], manuscript_uri))
                
                return event_uri
            
            return timespan_uri
        
        return None
    
    def add_generic_event(
        self,
        manuscript_uri: URIRef,
        event: Event,
        index: int = 0
    ) -> URIRef:
        """Add any event type based on EventClass"""
        event_uri = URIRef(create_event_uri(
            self.base_uri,
            event.manuscript_id,
            event.event_type,
            index
        ))
        
        # Add event class
        if event.event_class.value.startswith("F"):
            self.graph.add((event_uri, RDF.type, self.ns.LRMOO[event.event_class.value]))
        else:
            self.graph.add((event_uri, RDF.type, self.ns.CRM[event.event_class.value]))
        
        # Link to manuscript (using property from event)
        property_name = event.properties.get("property_to_manuscript", "P16_used_specific_object")
        if property_name.startswith("R"):
            self.graph.add((event_uri, self.ns.LRMOO[property_name], manuscript_uri))
        else:
            self.graph.add((event_uri, self.ns.CRM[property_name], manuscript_uri))
        
        # Add temporal info
        if event.date:
            timespan_uri = URIRef(create_timespan_uri(self.base_uri, event.date))
            self.graph.add((timespan_uri, RDF.type, self.ns.CRM.E52_Time_Span))
            self.graph.add((timespan_uri, RDFS.label, Literal(event.date)))
            self.graph.add((event_uri, self.ns.CRM.P4_has_time_span, timespan_uri))
        
        # Add spatial info
        if event.place:
            place_uri = self.add_place(event.place)
            self.graph.add((event_uri, self.ns.CRM.P7_took_place_at, place_uri))
        
        # Add actor
        if event.actor:
            actor_uri = self.add_person(event.actor)
            self.graph.add((event_uri, self.ns.CRM.P14_carried_out_by, actor_uri))
        
        # Label
        self.graph.add((event_uri, RDFS.label, 
                       Literal(f"{event.event_type} of MS {event.manuscript_id}", lang="en")))
        
        return event_uri
    
    def build_manuscript_graph(self, manuscript: Manuscript) -> None:
        """Build complete RDF graph for a manuscript"""
        # Add manuscript
        ms_uri = self.add_manuscript(manuscript)
        
        # Add colophon if present
        if manuscript.colophon:
            self.add_colophon(ms_uri, manuscript, manuscript.colophon)
        
        # Add work-expression-manifestation hierarchy
        if manuscript.work:
            self.add_work_expression_manifestation(ms_uri, manuscript, manuscript.work)
        
        # Add all events
        event_counter = {}
        for event in manuscript.events:
            event_type = event.event_type
            index = event_counter.get(event_type, 0)
            self.add_generic_event(ms_uri, event, index)
            event_counter[event_type] = index + 1
    
    def serialize(self, format: str = 'turtle') -> str:
        """Serialize graph to string"""
        return self.graph.serialize(format=format)
    
    def save(self, filepath: str, format: str = 'turtle') -> None:
        """Save graph to file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.serialize(format=format))
    
    @property
    def triple_count(self) -> int:
        """Get total number of triples"""
        return len(self.graph)
