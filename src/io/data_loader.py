"""
Data I/O Module - Isolated Side Effects
Handles all file operations (reading/writing)
"""

import pandas as pd
from typing import List, Dict, Optional
from pathlib import Path

from ..models.entities import Manuscript, ExtractionResult, ExtractedEntity, ClassifiedEntity, EntityType


# ============================================================================
# INPUT OPERATIONS
# ============================================================================

# Define which fields are "note" fields (where new data is found)
# vs structured MARC fields (where data already exists)
NOTE_FIELDS = frozenset([
    "957$a",  # Summary/abstract (Hebrew)
    "500$a",  # General notes
    "561$a",  # Provenance notes
])

# Structured MARC fields (non-note fields)
STRUCTURED_DATE_FIELDS = frozenset([
    "046$a", "046$b", "046$d", "260$c", "264$c", "008"
])

STRUCTURED_LOCATION_FIELDS = frozenset([
    "651$a", "751$a", "260$a", "264$a", "034$a"
])

STRUCTURED_PERSON_FIELDS = frozenset([
    "100$a", "600$a", "700$a", "710$a", "100$e", "700$e"
])


def load_excel_data(
    filepath: str,
    id_column: str = "001",
    notes_columns: List[str] = None,
    passthrough_columns: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Load manuscript data from Excel file
    
    Args:
        filepath: Path to Excel file
        id_column: Column containing manuscript IDs
        notes_columns: List of columns containing notes text (will be combined)
        passthrough_columns: Additional columns to preserve
        
    Returns:
        DataFrame with manuscript data (includes 'combined_notes' column and field maps)
    """
    if notes_columns is None:
        # Expanded to include fields where locations/persons/dates appear
        # This provides context for proper entity classification
        notes_columns = [
            "957$a",  # Summary/abstract (Hebrew)
            "500$a",  # General notes
            "561$a",  # Provenance notes
            "518$a",  # Date/time and place of event
            "561$3",  # Materials specified (provenance)
            "544$a",  # Location of other archival materials
            "541$a",  # Immediate source of acquisition
            "245$a",  # Title statement
            "245$c",  # Statement of responsibility
            "260$a",  # Place of publication/production
            "264$a",  # Production/publication place
            "651$a",  # Geographic name subject
            "751$a",  # Added entry - geographic name
            "700$e",  # Relator term (role of person)
            "710$e",  # Relator term (role of organization)
        ]
    
    try:
        df = pd.read_excel(filepath)
    except Exception as e:
        raise IOError(f"Failed to load Excel file: {e}")
    
    # Validate required columns
    if id_column not in df.columns:
        raise ValueError(f"ID column '{id_column}' not found in Excel")
    
    # Check which note columns exist
    existing_notes_columns = [col for col in notes_columns if col in df.columns]
    if not existing_notes_columns:
        raise ValueError(f"None of the notes columns {notes_columns} found in Excel")
    
    print(f"  Note fields found: {', '.join(existing_notes_columns)}")
    
    # Combine notes from all available columns
    def combine_notes(row):
        """Combine text from multiple note fields"""
        parts = []
        for col in existing_notes_columns:
            value = row.get(col, "")
            if pd.notna(value) and str(value).strip():
                parts.append(str(value).strip())
        return " | ".join(parts) if parts else ""
    
    df['combined_notes'] = df.apply(combine_notes, axis=1)
    
    # Create field content maps for tracking where entities came from
    def create_field_map(row):
        """Create a mapping of field -> content for entity source tracking"""
        field_map = {}
        for col in df.columns:
            value = row.get(col, "")
            if pd.notna(value) and str(value).strip():
                field_map[col] = str(value).strip()
        return field_map
    
    df['_field_map'] = df.apply(create_field_map, axis=1)
    
    # Filter out rows with no notes
    df = df[df['combined_notes'].str.strip() != ""]
    
    return df


def load_gazetteer(filepath: str, column: str = "location") -> frozenset:
    """
    Load location gazetteer from CSV
    
    Args:
        filepath: Path to gazetteer CSV
        column: Column containing location names
        
    Returns:
        Immutable set of location names
    """
    if not filepath or not Path(filepath).exists():
        return frozenset()
    
    try:
        df = pd.read_csv(filepath)
        if column in df.columns:
            locations = df[column].dropna().unique().tolist()
            return frozenset(locations)
    except Exception as e:
        print(f"Warning: Could not load gazetteer: {e}")
    
    return frozenset()


# ============================================================================
# OUTPUT OPERATIONS
# ============================================================================

def save_csv(df: pd.DataFrame, filepath: str) -> None:
    """Save DataFrame to CSV file"""
    output_dir = Path(filepath).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False, encoding='utf-8')
    print(f"✓ Saved: {filepath}")


def get_entity_source_field(entity_value: str, source_metadata: Dict, entity_type: str) -> str:
    """
    Determine which MARC field an entity came from
    
    Args:
        entity_value: The extracted entity value
        source_metadata: MARC field data for this manuscript
        entity_type: Type of entity ('date', 'location', 'person')
        
    Returns:
        Field name if found in non-note field, "new data" if only in note fields
    """
    # Determine which structured fields to check based on entity type
    if entity_type == 'date':
        structured_fields = STRUCTURED_DATE_FIELDS
    elif entity_type == 'location':
        structured_fields = STRUCTURED_LOCATION_FIELDS
    elif entity_type == 'person':
        structured_fields = STRUCTURED_PERSON_FIELDS
    else:
        return "new data"
    
    # Check if entity appears in any non-note (structured) field
    found_in_fields = []
    for field in structured_fields:
        if field in source_metadata:
            field_value = str(source_metadata[field])
            # Check if entity value appears in this field
            if entity_value in field_value or any(part in field_value for part in entity_value.split()):
                found_in_fields.append(field)
    
    if found_in_fields:
        # Found in structured field(s) - return field name(s)
        return "; ".join(found_in_fields)
    else:
        # Only found in note fields - mark as new data
        return "new data"


def manuscripts_to_dataframe(
    manuscripts: List[Manuscript], 
    classified_map: Optional[Dict[str, List[ClassifiedEntity]]] = None
) -> pd.DataFrame:
    """
    Convert manuscripts to flat DataFrame for CSV export
    
    Args:
        manuscripts: List of Manuscript objects
        classified_map: Optional map of classifications for embedded format
        
    Returns:
        DataFrame with extracted information
    """
    rows = []
    
    for ms in manuscripts:
        # Get classifications if available, otherwise use defaults
        classification_map = {}
        if classified_map and ms.manuscript_id in classified_map:
            classified_entities = classified_map[ms.manuscript_id]
            classification_map = {ce.value: ce.label for ce in classified_entities}
        
        # Format: "value | classification | source_field"
        dates_str = ", ".join(
            f"{e.value} | {classification_map.get(e.value, 'unclassified')} | {get_entity_source_field(e.value, ms.source_metadata, 'date')}" 
            for e in ms.dates
        ) if ms.dates else ""
        
        locations_str = ", ".join(
            f"{e.value} | {classification_map.get(e.value, 'unclassified')} | {get_entity_source_field(e.value, ms.source_metadata, 'location')}" 
            for e in ms.locations
        ) if ms.locations else ""
        
        persons_str = ", ".join(
            f"{p.full_name} | {classification_map.get(p.name, p.role if p.role else 'extracted_person')} | {get_entity_source_field(p.name, ms.source_metadata, 'person')}" 
            for p in ms.persons
        ) if ms.persons else ""
        
        row = {
            "manuscript_id": ms.manuscript_id,
            "notes_text": ms.notes_text,
            
            # Extracted entities with classifications AND source fields
            "dates": dates_str,
            "locations": locations_str,
            "persons": persons_str,
            
            # Structured information
            "has_colophon": ms.has_colophon,
            "scribe_name": ms.primary_scribe.full_name if ms.primary_scribe else "",
            "work_title": ms.work.title if ms.work else "",
            
            # Event count
            "num_events": len(ms.events),
            "production_events": len(ms.production_events),
        }
        
        # Add source metadata
        row.update(ms.source_metadata)
        
        rows.append(row)
    
    return pd.DataFrame(rows)


def events_to_dataframe(manuscripts: List[Manuscript]) -> pd.DataFrame:
    """
    Convert all events to structured DataFrame
    
    Args:
        manuscripts: List of Manuscript objects
        
    Returns:
        DataFrame with all events
    """
    rows = []
    
    for ms in manuscripts:
        for event in ms.events:
            row = {
                "manuscript_id": ms.manuscript_id,
                "event_type": event.event_type,
                "event_class": event.event_class.value,
                "date": event.date or "",
                "place": event.place.name if event.place else "",
                "actor": event.actor.full_name if event.actor else "",
                "has_temporal_info": event.has_temporal_info,
                "has_spatial_info": event.has_spatial_info,
            }
            rows.append(row)
    
    return pd.DataFrame(rows)


def classified_entities_to_dataframe(
    manuscripts: List[Manuscript],
    classified_dates: Dict[str, List],
    classified_locations: Dict[str, List]
) -> pd.DataFrame:
    """
    Add classification information to manuscripts DataFrame
    
    Args:
        manuscripts: List of Manuscript objects
        classified_dates: Mapping of manuscript_id to classified dates
        classified_locations: Mapping of manuscript_id to classified locations
        
    Returns:
        DataFrame with classification columns
    """
    rows = []
    
    for ms in manuscripts:
        ms_id = ms.manuscript_id
        
        # Format date classifications
        date_relations = []
        if ms_id in classified_dates:
            date_relations = [
                f"{ce.value}|{ce.label}" 
                for ce in classified_dates[ms_id]
            ]
        
        # Format location classifications
        loc_relations = []
        if ms_id in classified_locations:
            loc_relations = [
                f"{ce.value}|{ce.label}" 
                for ce in classified_locations[ms_id]
            ]
        
        # Event classes
        event_classes = [e.event_class.value for e in ms.events]
        
        row = {
            "manuscript_id": ms_id,
            "date_relations": "; ".join(date_relations),
            "location_relations": "; ".join(loc_relations),
            "event_classes": "; ".join(event_classes),
        }
        
        rows.append(row)
    
    return pd.DataFrame(rows)


def create_detailed_entities_dataframe(
    manuscripts: List[Manuscript],
    classified_map: Dict[str, List[ClassifiedEntity]]
) -> pd.DataFrame:
    """
    Create detailed entities DataFrame with classifications embedded in entity columns
    Format: "value1 | classification1, value2 | classification2"
    
    Args:
        manuscripts: List of manuscripts
        classified_map: Map of manuscript_id to classified entities
        
    Returns:
        DataFrame with manuscript-centric view of classified entities
    """
    rows = []
    
    for ms in manuscripts:
        ms_id = ms.manuscript_id
        source_meta = ms.source_metadata
        
        # Get classifications for this manuscript
        classified_entities = classified_map.get(ms_id, [])
        
        # Create a map of entity value -> classification label
        classification_map = {ce.value: ce.label for ce in classified_entities}
        
        # Process dates - create "value | classification | source_field" format
        date_entries = []
        for date_entity in ms.dates:
            date_value = date_entity.value
            classification = classification_map.get(date_value, "unclassified")
            source_field = get_entity_source_field(date_value, source_meta, 'date')
            date_entries.append(f"{date_value} | {classification} | {source_field}")
        
        # Process locations - create "value | classification | source_field" format
        location_entries = []
        for loc_entity in ms.locations:
            loc_value = loc_entity.value
            classification = classification_map.get(loc_value, "unclassified")
            source_field = get_entity_source_field(loc_value, source_meta, 'location')
            location_entries.append(f"{loc_value} | {classification} | {source_field}")
        
        # Process persons - create "value | classification | source_field" format
        person_entries = []
        for person in ms.persons:
            person_name = person.name
            # Check if person was classified
            classification = classification_map.get(person_name, person.role if person.role else "extracted_person")
            source_field = get_entity_source_field(person_name, source_meta, 'person')
            person_entries.append(f"{person_name} | {classification} | {source_field}")
        
        # Only add row if there are any entities
        if date_entries or location_entries or person_entries:
            rows.append({
                'manuscript_id': ms_id,
                'dates': ', '.join(date_entries) if date_entries else '',
                'locations': ', '.join(location_entries) if location_entries else '',
                'persons': ', '.join(person_entries) if person_entries else ''
            })
    
    return pd.DataFrame(rows)


def save_extraction_results(
    result: ExtractionResult,
    output_dir: str,
    prefix: str = "manuscript_extraction",
    classified_map: Optional[Dict[str, List[ClassifiedEntity]]] = None
) -> Dict[str, str]:
    """
    Save complete extraction results to multiple files
    
    Args:
        result: ExtractionResult object
        output_dir: Output directory path
        prefix: Filename prefix
        classified_map: Optional map of classifications for detailed export
        
    Returns:
        Dictionary of saved file paths
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    saved_files = {}
    
    # Main manuscripts CSV (with classifications if available)
    manuscripts_df = manuscripts_to_dataframe(result.manuscripts, classified_map)
    main_path = output_path / f"{prefix}_entities.csv"
    save_csv(manuscripts_df, str(main_path))
    saved_files["entities"] = str(main_path)
    
    # Detailed entities CSV with classifications (if available)
    if classified_map:
        detailed_entities_df = create_detailed_entities_dataframe(result.manuscripts, classified_map)
        detailed_path = output_path / f"{prefix}_entities_detailed.csv"
        save_csv(detailed_entities_df, str(detailed_path))
        saved_files["entities_detailed"] = str(detailed_path)
    
    # Events CSV
    events_df = events_to_dataframe(result.manuscripts)
    events_path = output_path / f"{prefix}_events.csv"
    save_csv(events_df, str(events_path))
    saved_files["events"] = str(events_path)
    
    # Summary statistics
    summary_df = pd.DataFrame([result.summary])
    summary_path = output_path / f"{prefix}_summary.csv"
    save_csv(summary_df, str(summary_path))
    saved_files["summary"] = str(summary_path)
    
    return saved_files


def explode_and_count(
    series: pd.Series,
    min_count: int = 1,
    separator: str = ";"
) -> pd.DataFrame:
    """
    Pure function: Explode semicolon-separated values and count
    
    Args:
        series: Pandas Series with delimited values
        min_count: Minimum occurrence count
        separator: Value separator
        
    Returns:
        DataFrame with value counts
    """
    all_values = []
    
    for val in series:
        if pd.notna(val) and str(val).strip():
            parts = str(val).split(separator)
            for p in parts:
                p = p.strip()
                if p:
                    all_values.append(p)
    
    if not all_values:
        return pd.DataFrame(columns=["value", "count"])
    
    counts = pd.Series(all_values).value_counts()
    counts = counts[counts >= min_count]
    
    return pd.DataFrame({
        "value": counts.index,
        "count": counts.values
    })


def save_frequency_tables(
    manuscripts_df: pd.DataFrame,
    output_dir: str,
    min_count: int = 2
) -> Dict[str, str]:
    """
    Save frequency tables for dates and locations
    
    Args:
        manuscripts_df: DataFrame with manuscripts data
        output_dir: Output directory
        min_count: Minimum occurrence count
        
    Returns:
        Dictionary of saved file paths
    """
    output_path = Path(output_dir)
    saved_files = {}
    
    # Dates frequency
    if "dates" in manuscripts_df.columns:
        dates_freq = explode_and_count(manuscripts_df["dates"], min_count)
        dates_path = output_path / "dates_frequency.csv"
        save_csv(dates_freq.head(100), str(dates_path))
        saved_files["dates"] = str(dates_path)
    
    # Locations frequency
    if "locations" in manuscripts_df.columns:
        locations_freq = explode_and_count(manuscripts_df["locations"], min_count)
        locations_path = output_path / "locations_frequency.csv"
        save_csv(locations_freq.head(100), str(locations_path))
        saved_files["locations"] = str(locations_path)
    
    return saved_files
