"""
Main Extraction Pipeline - Functional Orchestration
Pure functional composition of extraction → classification → RDF generation
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

from .models.entities import (
    Manuscript, ExtractedEntity, ClassifiedEntity, Person, Place, 
    Work, Event, EventClass, ColophonInfo, ExtractionResult, Config
)
from .extractors.text_extractors import (
    extract_dates, extract_locations, extract_person_mentions,
    extract_colophon_info, extract_work_title, extract_locations_with_kima
)
from .extractors.ai_extractor import (
    create_ai_extractor, extract_batch_with_ai
)
from .classification.grok_classifier import create_classifier, get_ontology_mapping
from .classification.hebrew_patterns import classify_person_by_patterns, classify_location_by_patterns
from .ontology.rdf_generator import RDFGraphBuilder, RDF_AVAILABLE
from .io.data_loader import (
    load_excel_data, load_gazetteer, save_extraction_results,
    manuscripts_to_dataframe, save_frequency_tables
)
from .io.kima_loader import KimaGazetteer


# ============================================================================
# CORE PIPELINE FUNCTIONS - Pure Transformations
# ============================================================================

def extract_entities_from_text(
    text: str,
    manuscript_id: str,
    gazetteer: frozenset,
    source_metadata: Dict[str, str],
    kima_gazetteer=None
) -> Manuscript:
    """
    Pure function: Extract all entities from manuscript text
    
    Args:
        text: Manuscript notes text
        manuscript_id: Manuscript identifier
        gazetteer: Location gazetteer (legacy)
        source_metadata: Passthrough metadata
        kima_gazetteer: Optional Kima gazetteer for enhanced location extraction
        
    Returns:
        Manuscript object with extracted entities
    """
    # Extract all entity types
    dates = extract_dates(text)
    
    # Location extraction: Use Kima if available, otherwise use legacy gazetteer
    if kima_gazetteer:
        locations = extract_locations_with_kima(text, kima_gazetteer)
    else:
        locations = extract_locations(text, gazetteer)
    
    persons = extract_person_mentions(text)
    colophon = extract_colophon_info(text)
    work_title = extract_work_title(text)
    
    # Create work object if title found
    work = Work(title=work_title) if work_title else None
    
    return Manuscript(
        manuscript_id=manuscript_id,
        notes_text=text,
        dates=dates,
        locations=locations,
        persons=persons,
        colophon=colophon,
        work=work,
        events=[],  # Will be populated after classification
        source_metadata=source_metadata
    )


def classify_entities(
    manuscripts: List[Manuscript],
    classifier
) -> Dict[str, List[ClassifiedEntity]]:
    """
    Classify extracted entities using Grok API
    
    Args:
        manuscripts: List of manuscripts with extracted entities
        classifier: GrokClassifier instance
        
    Returns:
        Dictionary mapping manuscript_id to classified entities
    """
    if not classifier:
        print("⚠ Classification disabled - no classifier provided")
        return {}
    
    print(f"Classifying entities for {len(manuscripts)} manuscripts...")
    
    all_classified = {}
    
    # Progress bar for manuscript processing
    for ms in tqdm(manuscripts, desc="Classifying manuscripts", unit="ms"):
        if not ms.dates and not ms.locations and not ms.persons:
            continue
        
        # Convert Person objects to ExtractedEntity objects for classification
        from .models.entities import EntityType
        person_entities = [
            ExtractedEntity(
                value=p.name,
                entity_type=EntityType.PERSON,
                context=ms.notes_text,
                confidence=1.0
            )
            for p in ms.persons
        ]
        
        # Combine dates, locations, AND persons
        all_entities = ms.dates + ms.locations + person_entities
        
        # Classify (now includes persons!)
        classified = classifier.classify_entities(ms.notes_text, all_entities)
        
        if classified:
            all_classified[ms.manuscript_id] = classified
    
    print(f"\n✓ Classified entities for {len(all_classified)} manuscripts")
    
    return all_classified


def classify_entities_hybrid(
    manuscripts: List[Manuscript],
    classifier
) -> Dict[str, List[ClassifiedEntity]]:
    """
    HYBRID classification: Hebrew patterns first, then Grok AI fallback
    
    Args:
        manuscripts: List of manuscripts with extracted entities
        classifier: GrokClassifier instance
        
    Returns:
        Dictionary mapping manuscript_id to classified entities
    """
    if not classifier:
        print("⚠ Classification disabled - no classifier provided")
        return {}
    
    print(f"🔀 HYBRID Classification for {len(manuscripts)} manuscripts...")
    print("  Step 1: Trying Hebrew pattern-based classification...")
    
    all_classified = {}
    needs_ai_classification = []  # Manuscripts that need AI help
    
    pattern_successes = 0
    pattern_attempts = 0
    location_pattern_successes = 0
    location_pattern_attempts = 0
    person_pattern_successes = 0
    person_pattern_attempts = 0
    
    # Phase 1: Try Hebrew patterns for all manuscripts
    for ms in tqdm(manuscripts, desc="Pattern classification", unit="ms"):
        if not ms.dates and not ms.locations and not ms.persons:
            continue
        
        classified_entities = []
        unclassified_entities = []
        
        # Try to classify persons with Hebrew patterns
        for person in ms.persons:
            person_pattern_attempts += 1
            pattern_attempts += 1
            role = classify_person_by_patterns(ms.notes_text, person.name)
            
            if role:
                # Pattern matched! Create classified entity
                person_pattern_successes += 1
                pattern_successes += 1
                from .models.entities import EntityType
                entity = ExtractedEntity(
                    value=person.name,
                    entity_type=EntityType.PERSON,
                    context=ms.notes_text,
                    confidence=0.9
                )
                
                # Get ontology mapping for this role
                ontology_mapping = get_ontology_mapping(role)
                
                classified = ClassifiedEntity(
                    entity=entity,
                    label=role,
                    ontology_mapping=ontology_mapping
                )
                classified_entities.append(classified)
            else:
                # No pattern matched - needs AI
                from .models.entities import EntityType
                entity = ExtractedEntity(
                    value=person.name,
                    entity_type=EntityType.PERSON,
                    context=ms.notes_text,
                    confidence=1.0
                )
                unclassified_entities.append(entity)
        
        # Try to classify locations with Hebrew patterns
        for location in ms.locations:
            location_pattern_attempts += 1
            pattern_attempts += 1
            role = classify_location_by_patterns(ms.notes_text, location.value)
            
            if role:
                # Pattern matched! Create classified entity
                location_pattern_successes += 1
                pattern_successes += 1
                from .models.entities import EntityType
                
                ontology_mapping = get_ontology_mapping(role)
                
                classified = ClassifiedEntity(
                    entity=location,
                    label=role,
                    ontology_mapping=ontology_mapping
                )
                classified_entities.append(classified)
            else:
                # No pattern matched - needs AI
                unclassified_entities.append(location)
        
        # Dates always need AI classification (no patterns yet)
        from .models.entities import EntityType
        unclassified_entities.extend(ms.dates)
        
        # If we have classified entities from patterns, store them
        if classified_entities:
            all_classified[ms.manuscript_id] = classified_entities
        
        # If we have unclassified entities, mark for AI processing
        if unclassified_entities:
            needs_ai_classification.append((ms, unclassified_entities))
    
    print(f"  ✓ Pattern classification:")
    print(f"    - Persons: {person_pattern_successes}/{person_pattern_attempts} classified ({100*person_pattern_successes/max(person_pattern_attempts,1):.1f}%)")
    print(f"    - Locations: {location_pattern_successes}/{location_pattern_attempts} classified ({100*location_pattern_successes/max(location_pattern_attempts,1):.1f}%)")
    print(f"    - Total: {pattern_successes}/{pattern_attempts} classified ({100*pattern_successes/max(pattern_attempts,1):.1f}%)")
    
    # Phase 2: Use Grok AI for remaining entities
    if needs_ai_classification:
        print(f"\n  Step 2: Using Grok AI for {len(needs_ai_classification)} manuscripts with unclassified entities...")
        
        for ms, unclassified in tqdm(needs_ai_classification, desc="AI classification", unit="ms"):
            # Classify using Grok
            ai_classified = classifier.classify_entities(ms.notes_text, unclassified)
            
            if ai_classified:
                # Merge with pattern-based classifications
                if ms.manuscript_id in all_classified:
                    all_classified[ms.manuscript_id].extend(ai_classified)
                else:
                    all_classified[ms.manuscript_id] = ai_classified
    else:
        print("  ✓ All entities classified by patterns - no AI needed!")
    
    print(f"\n✓ Total classified: {len(all_classified)} manuscripts")
    
    return all_classified


def create_events_from_classified(
    manuscript: Manuscript,
    classified_entities: List[ClassifiedEntity]
) -> List[Event]:
    """
    Pure function: Create Event objects from classified entities
    
    Args:
        manuscript: Manuscript object
        classified_entities: List of classified entities
        
    Returns:
        List of Event objects
    """
    events: List[Event] = []
    
    # Group by event type
    events_by_type = defaultdict(list)
    
    for classified in classified_entities:
        ontology_mapping = classified.ontology_mapping
        event_class_name = ontology_mapping.get("event_class", "E7_Activity")
        
        # Try to get EventClass enum
        try:
            event_class = EventClass(event_class_name)
        except ValueError:
            event_class = EventClass.E7_ACTIVITY
        
        event_type = classified.label.replace(" date", "").replace(" in", "")
        
        # Create event
        if classified.entity_type.value == "date":
            event = Event(
                event_type=event_type,
                event_class=event_class,
                manuscript_id=manuscript.manuscript_id,
                date=classified.value,
                properties=ontology_mapping
            )
            events.append(event)
        elif classified.entity_type.value == "location":
            # Find matching date event if any
            place = Place(name=classified.value)
            
            # Create location-based event or attach to existing
            event = Event(
                event_type=event_type,
                event_class=event_class,
                manuscript_id=manuscript.manuscript_id,
                place=place,
                properties=ontology_mapping
            )
            events.append(event)
    
    return events


def enrich_manuscript_with_classification(
    manuscript: Manuscript,
    classified_entities: List[ClassifiedEntity]
) -> Manuscript:
    """
    Pure function: Create new Manuscript with events from classification
    
    Args:
        manuscript: Original manuscript
        classified_entities: Classified entities
        
    Returns:
        New Manuscript with events
    """
    events = create_events_from_classified(manuscript, classified_entities)
    
    # Create new manuscript with events (immutable update)
    return Manuscript(
        manuscript_id=manuscript.manuscript_id,
        notes_text=manuscript.notes_text,
        dates=manuscript.dates,
        locations=manuscript.locations,
        persons=manuscript.persons,
        colophon=manuscript.colophon,
        work=manuscript.work,
        expression=manuscript.expression,
        events=events,
        nli_uri=manuscript.nli_uri,
        source_metadata=manuscript.source_metadata
    )


def build_knowledge_graph(
    manuscripts: List[Manuscript],
    config: Config
) -> Optional[RDFGraphBuilder]:
    """
    Build RDF knowledge graph from manuscripts
    
    Args:
        manuscripts: List of manuscripts with events
        config: Application configuration
        
    Returns:
        RDFGraphBuilder with complete graph
    """
    if not RDF_AVAILABLE:
        print("⚠ RDF generation disabled - rdflib not available")
        return None
    
    print(f"Building RDF knowledge graph...")
    
    builder = RDFGraphBuilder(config)
    
    for ms in manuscripts:
        builder.build_manuscript_graph(ms)
    
    print(f"✓ Knowledge graph built: {builder.triple_count} triples")
    
    return builder


# ============================================================================
# MAIN PIPELINE ORCHESTRATION
# ============================================================================

def run_extraction_pipeline(config: Config, max_manuscripts: Optional[int] = None) -> ExtractionResult:
    """
    Main extraction pipeline - orchestrates all steps
    
    Args:
        config: Application configuration
        max_manuscripts: Optional limit on number of manuscripts to process
        
    Returns:
        ExtractionResult with complete extraction data
    """
    print("\n" + "="*80)
    print("HEBREW MANUSCRIPT ENTITY EXTRACTION PIPELINE")
    print("="*80 + "\n")
    
    # Validate configuration
    config.validate()
    
    # Step 1: Load data
    print("Step 1: Loading data...")
    df = load_excel_data(
        config.input_excel_path,
        id_column="001",
        notes_columns=["957$a", "500$a", "561$a"]  # Multiple note fields
    )
    
    # Limit manuscripts if requested (for testing)
    if max_manuscripts and len(df) > max_manuscripts:
        print(f"📊 TEST MODE: Limiting to first {max_manuscripts} manuscripts")
        df = df.head(max_manuscripts)
    
    print(f"✓ Loaded {len(df)} manuscripts")
    
    # Load gazetteer (legacy or Kima)
    kima_gazetteer = None
    if config.use_kima:
        # Load Kima/Maagarim gazetteer
        import os
        kima_dir = os.path.join(os.path.dirname(config.input_excel_path), "input", "sinai")
        if not os.path.exists(kima_dir):
            # Try alternative path
            kima_dir = os.path.join("data", "input", "sinai")
        
        if os.path.exists(kima_dir):
            print("Loading Kima/Maagarim comprehensive gazetteer...")
            try:
                kima_gazetteer = KimaGazetteer(kima_dir)
                stats = kima_gazetteer.get_statistics()
                print(f"✓ Loaded Kima gazetteer:")
                print(f"  - {stats['total_places']:,} canonical places")
                print(f"  - {stats['total_variants']:,} Hebrew variants")
                print(f"  - {stats['total_textual_forms']:,} textual forms")
                print(f"  - {stats['total_lookups']:,} total lookup entries")
                print(f"  - {stats['places_with_wikidata']:,} with Wikidata links ({100*stats['places_with_wikidata']/stats['total_places']:.1f}%)")
                print(f"  - {stats['places_with_coords']:,} with coordinates ({100*stats['places_with_coords']/stats['total_places']:.1f}%)")
            except FileNotFoundError as e:
                print(f"[WARNING] Kima data not found: {e}")
                print(f"  Expected location: {kima_dir}")
                print("  Falling back to legacy gazetteer...")
                config.use_kima = False
        else:
            print(f"[WARNING] Kima data directory not found: {kima_dir}")
            print("  Falling back to legacy gazetteer...")
            config.use_kima = False
    
    # Load legacy gazetteer if not using Kima
    gazetteer = frozenset()
    if not config.use_kima:
        gazetteer = load_gazetteer(config.gazetteer_path) if config.gazetteer_path else frozenset()
        print(f"✓ Loaded legacy gazetteer: {len(gazetteer)} locations")
    
    # Step 2: Extract entities
    print("\nStep 2: Extracting entities...")
    manuscripts: List[Manuscript] = []
    
    if config.ai_only:
        # AI-ONLY MODE: Use Grok for complete extraction
        print("🤖 AI-ONLY MODE: Using Grok for entity extraction")
        
        # Create fallback directory for failed JSON responses
        import os
        fallback_dir = os.path.join(config.output_dir, "ai_fallback_responses")
        
        # Create AI extractor
        ai_extractor = create_ai_extractor(
            api_key=config.grok_api_key,
            max_retries=config.grok_retries,
            timeout=config.grok_timeout,
            fallback_dir=fallback_dir
        )
        print(f"  → Fallback responses will be saved to: {fallback_dir}")
        
        # Prepare data for batch extraction
        texts_data = []
        for idx, row in df.iterrows():
            text = str(row.get("combined_notes", ""))
            ms_id = str(row.get("001", f"MS_{idx}"))
            
            # Get source metadata (exclude combined notes and ID)
            source_metadata = {
                col: str(row.get(col, ""))
                for col in df.columns
                if col not in ["combined_notes", "001"]
            }
            
            texts_data.append((text, ms_id, source_metadata))
        
        # Extract using AI (returns manuscripts AND classified entities)
        manuscripts, classified_map = extract_batch_with_ai(
            texts=texts_data,
            extractor=ai_extractor,
            show_progress=True
        )
        
        print(f"✓ AI extracted {len(manuscripts)} manuscripts with classifications")
        
    else:
        # REGEX MODE: Use pattern-based extraction
        print("📝 REGEX MODE: Using pattern-based extraction")
        
        classified_map = {}  # Will be populated in classification step
        
        for idx, row in df.iterrows():
            text = str(row.get("combined_notes", ""))
            ms_id = str(row.get("001", f"MS_{idx}"))
            
            # Get source metadata (exclude combined notes and ID)
            source_metadata = {
                col: str(row.get(col, ""))
                for col in df.columns
                if col not in ["combined_notes", "001"]
            }
            
            manuscript = extract_entities_from_text(
                text, ms_id, gazetteer, source_metadata, kima_gazetteer
            )
            manuscripts.append(manuscript)
    
    print(f"✓ Extracted entities from {len(manuscripts)} manuscripts")
    print(f"  - Total dates: {sum(len(m.dates) for m in manuscripts)}")
    print(f"  - Total locations: {sum(len(m.locations) for m in manuscripts)}")
    print(f"  - Total persons: {sum(len(m.persons) for m in manuscripts)}")
    print(f"  - Colophons found: {sum(1 for m in manuscripts if m.has_colophon)}")
    
    # Step 3: Classify entities (optional in AI-only mode)
    if config.ai_only:
        print("\nStep 3: Using AI-provided classifications (already extracted with semantic types)")
        # classified_map already populated from AI extraction
        print(f"  ✓ {len(classified_map)} manuscripts have classified entities")
    elif config.use_kima:
        # HYBRID MODE: Pattern-based classification with AI fallback
        print("\nStep 3: Hybrid classification (Hebrew patterns + AI fallback)...")
        classifier = create_classifier(config)
        classified_map = classify_entities_hybrid(manuscripts, classifier)
    else:
        # STANDARD MODE: Pure AI classification
        print("\nStep 3: Classifying entities with Grok...")
        classifier = create_classifier(config)
        classified_map = classify_entities(manuscripts, classifier)
    
    # Enrich manuscripts with events
    enriched_manuscripts = []
    for ms in manuscripts:
        if ms.manuscript_id in classified_map:
            enriched = enrich_manuscript_with_classification(
                ms, 
                classified_map[ms.manuscript_id]
            )
            enriched_manuscripts.append(enriched)
        else:
            enriched_manuscripts.append(ms)
    
    manuscripts = enriched_manuscripts
    
    total_events = sum(len(m.events) for m in manuscripts)
    print(f"✓ Created {total_events} structured events")
    
    # Step 4: Build RDF knowledge graph
    print("\nStep 4: Building RDF knowledge graph...")
    graph_builder = build_knowledge_graph(manuscripts, config)
    
    # Step 5: Save outputs
    print("\nStep 5: Saving outputs...")
    
    # Save CSVs (with classification map for detailed export)
    saved_files = save_extraction_results(
        ExtractionResult(
            manuscripts=manuscripts,
            extraction_date=datetime.now(),
            total_dates_extracted=sum(len(m.dates) for m in manuscripts),
            total_locations_extracted=sum(len(m.locations) for m in manuscripts),
            total_persons_extracted=sum(len(m.persons) for m in manuscripts),
            total_events_created=total_events
        ),
        output_dir=config.output_dir,
        classified_map=classified_map if classified_map else None
    )
    
    # Save frequency tables
    manuscripts_df = manuscripts_to_dataframe(manuscripts, classified_map if classified_map else None)
    freq_files = save_frequency_tables(manuscripts_df, config.output_dir)
    saved_files.update(freq_files)
    
    # Save RDF outputs
    if graph_builder:
        # Turtle format
        turtle_path = f"{config.output_dir}/knowledge_graph.ttl"
        graph_builder.save(turtle_path, format='turtle')
        saved_files["rdf_turtle"] = turtle_path
        print(f"✓ Saved: {turtle_path}")
        
        # JSON-LD format
        jsonld_path = f"{config.output_dir}/knowledge_graph.jsonld"
        graph_builder.save(jsonld_path, format='json-ld')
        saved_files["rdf_jsonld"] = jsonld_path
        print(f"✓ Saved: {jsonld_path}")
    
    # Final summary
    print("\n" + "="*80)
    print("✓ EXTRACTION COMPLETE")
    print("="*80)
    print(f"\nSummary:")
    print(f"  - Manuscripts processed: {len(manuscripts)}")
    print(f"  - Dates extracted: {sum(len(m.dates) for m in manuscripts)}")
    print(f"  - Locations extracted: {sum(len(m.locations) for m in manuscripts)}")
    print(f"  - Persons extracted: {sum(len(m.persons) for m in manuscripts)}")
    print(f"  - Events created: {total_events}")
    print(f"  - Colophons detected: {sum(1 for m in manuscripts if m.has_colophon)}")
    if graph_builder:
        print(f"  - RDF triples: {graph_builder.triple_count}")
    
    print(f"\nOutputs saved to: {config.output_dir}")
    for key, path in saved_files.items():
        print(f"  - {key}: {path}")
    
    return ExtractionResult(
        manuscripts=manuscripts,
        extraction_date=datetime.now(),
        total_dates_extracted=sum(len(m.dates) for m in manuscripts),
        total_locations_extracted=sum(len(m.locations) for m in manuscripts),
        total_persons_extracted=sum(len(m.persons) for m in manuscripts),
        total_events_created=total_events
    )
