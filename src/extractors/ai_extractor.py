"""
AI-Based Entity Extraction using Grok API
Complete extraction without regex patterns - AI extracts all entities directly
"""

import json
import time
import requests
from typing import List, Dict, Optional, Tuple
from functools import lru_cache

from ..models.entities import (
    ExtractedEntity, EntityType, Person, ColophonInfo, 
    Manuscript, Work
)


# ============================================================================
# GROK API EXTRACTION PROMPTS
# ============================================================================

EXTRACTION_SYSTEM_PROMPT = """You are an expert in Hebrew manuscript cataloging and paleography.
Your task is to extract structured information from Hebrew manuscript catalog notes with semantic classification.

Extract the following information when present:
1. DATES - Any dates mentioned WITH their event type
2. LOCATIONS - Geographic places WITH their relationship type
3. PERSONS - Names of people WITH their roles
4. COLOPHON - Whether text contains a colophon (completion statement)
5. WORK_TITLE - Title of the work/text

Return ONLY valid JSON with this exact structure:
{
  "dates": [{"value": "1407", "event_type": "manuscript production date", "confidence": 0.95, "context": "surrounding text"}],
  "locations": [{"value": "קנדיה", "relationship": "produced in", "confidence": 0.9, "context": "surrounding text"}],
  "persons": [{"name": "משה", "patronymic": "יצחק", "role": "scribe", "confidence": 0.95}],
  "colophon": {"present": true, "text": "colophon text", "markers": ["נשלם"]},
  "work_title": {"title": "גינת אגוז", "confidence": 0.85}
}

DATE EVENT TYPES (choose the most appropriate):
- "manuscript production date" - when the physical manuscript was written/copied
- "work creation date" - when the intellectual work was composed
- "publication date" / "printing date" - when printed/published
- "binding date" / "restoration date" - physical modifications
- "acquisition date" / "purchase date" / "donation date" - ownership transfer
- "birth date" / "death date" - person life events
- "cataloging date" - when cataloged
- Or use descriptive phrase if none fit (e.g., "letter writing date")

LOCATION RELATIONSHIP TYPES (choose the most appropriate):
- "produced in" / "written in" / "copied in" - where manuscript was made
- "published in" / "printed in" - publication location
- "owned in" - ownership location
- "donated in" - donation location
- "acquired in" / "purchased in" - acquisition location
- "bound in" - binding location
- "resided in" / "active in" - person's location
- Or use descriptive phrase if none fit (e.g., "mentioned in")

PERSON ROLES (already working correctly):
- "scribe", "author", "editor", "owner", "donor", "translator", etc.

Rules:
- Extract Hebrew text exactly as it appears
- ALWAYS provide event_type for dates and relationship for locations
- Include confidence scores (0.0-1.0)
- Include surrounding context (5-10 words) for each entity
- For persons, extract name, patronymic (if present), and inferred role
- Mark colophon presence and extract its text
- Choose the most specific and appropriate type/relationship based on context
- If uncertain about type, use the most general option ("manuscript production date", "produced in")
- Only extract entities that are clearly present in the text
- Return empty arrays/null for missing information
- Do NOT invent information not in the text
"""

EXTRACTION_USER_PROMPT_TEMPLATE = """Extract structured entities from this Hebrew manuscript catalog note:

TEXT: {text}

Return JSON with extracted entities following the specified format."""


# ============================================================================
# GROK API INTERACTION
# ============================================================================

class GrokAIExtractor:
    """AI-based entity extractor using Grok API"""
    
    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.x.ai/v1/chat/completions",
        model: str = "grok-4-fast-non-reasoning",
        max_retries: int = 3,
        timeout: int = 45,
        fallback_dir: Optional[str] = None
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.fallback_dir = fallback_dir
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Create fallback directory if specified
        if self.fallback_dir:
            from pathlib import Path
            Path(self.fallback_dir).mkdir(parents=True, exist_ok=True)
    
    def extract_from_text(
        self, 
        text: str,
        manuscript_id: str = ""
    ) -> Dict:
        """
        Extract all entities from text using Grok AI
        
        Args:
            text: Manuscript notes text
            manuscript_id: Manuscript identifier (for logging)
            
        Returns:
            Dictionary with extracted entities
        """
        if not text or not text.strip():
            return self._empty_response()
        
        prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(text=text)
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,  # Low temperature for factual extraction
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}
        }
        
        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    
                    # Parse JSON response
                    try:
                        # Try to repair common JSON issues before parsing
                        repaired_content = self._repair_json(content)
                        extracted_data = json.loads(repaired_content)
                        return self._validate_response(extracted_data)
                    except json.JSONDecodeError as e:
                        print(f"⚠ JSON parse error for {manuscript_id}: {e}")
                        
                        # Save raw response for debugging
                        if self.fallback_dir:
                            self._save_raw_response(manuscript_id, content, str(e))
                        
                        # Try text-based fallback extraction
                        fallback_data = self._fallback_text_extraction(content, manuscript_id)
                        if fallback_data and any(fallback_data.values()):
                            print(f"✓ Fallback extraction succeeded for {manuscript_id}")
                            return fallback_data
                        
                        # Retry if we still have attempts left
                        if attempt < self.max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        
                        # Last resort: return empty with saved raw data
                        return self._empty_response()
                
                elif response.status_code == 429:  # Rate limit
                    wait_time = 2 ** attempt
                    print(f"⚠ Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                    
                else:
                    print(f"⚠ API error {response.status_code}: {response.text}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return self._empty_response()
                    
            except requests.exceptions.Timeout:
                print(f"⚠ Timeout for {manuscript_id}, attempt {attempt + 1}")
                if attempt < self.max_retries - 1:
                    continue
                return self._empty_response()
                
            except Exception as e:
                print(f"⚠ Extraction error for {manuscript_id}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return self._empty_response()
        
        return self._empty_response()
    
    def _empty_response(self) -> Dict:
        """Return empty response structure"""
        return {
            "dates": [],
            "locations": [],
            "persons": [],
            "colophon": None,
            "work_title": None
        }
    
    def _repair_json(self, content: str) -> str:
        """
        Repair common JSON errors in AI responses
        
        Common issues:
        1. Double quotes in Hebrew abbreviations: כה""י → כה"י
        2. Escaped quotes that should be single: י""א → י"א
        3. Multiple consecutive double quotes
        
        Args:
            content: Raw JSON string from AI
            
        Returns:
            Repaired JSON string
        """
        import re
        
        # Fix Hebrew abbreviations with doubled quotes
        # Pattern: Hebrew letter(s) followed by "" followed by Hebrew letter(s)
        # Examples: כה""י, י""א, התל""ג"", כמה""ר
        
        # Strategy: Inside JSON string values, replace "" with "
        # But ONLY between Hebrew characters (to avoid breaking actual JSON structure)
        
        # Hebrew Unicode range: \u0590-\u05FF
        hebrew_pattern = r'[\u0590-\u05FF]'
        
        # Simpler strategy: Replace all "" with \" globally
        # This works because "" only appears in Hebrew abbreviations within string values
        # Never in actual JSON structure (where we'd have \" for escaped quotes)
        
        repaired = content.replace('""', '\\"')
        
        return repaired
    
    def _validate_response(self, data: Dict) -> Dict:
        """Validate and normalize AI response"""
        validated = {
            "dates": data.get("dates", []),
            "locations": data.get("locations", []),
            "persons": data.get("persons", []),
            "colophon": data.get("colophon"),
            "work_title": data.get("work_title")
        }
        
        # Ensure lists
        for key in ["dates", "locations", "persons"]:
            if not isinstance(validated[key], list):
                validated[key] = []
        
        return validated
    
    def _save_raw_response(self, manuscript_id: str, content: str, error: str):
        """Save raw AI response when JSON parsing fails"""
        try:
            from pathlib import Path
            import datetime
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{manuscript_id}_{timestamp}.txt"
            filepath = Path(self.fallback_dir) / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"=== JSON Parse Error ===\n")
                f.write(f"Manuscript ID: {manuscript_id}\n")
                f.write(f"Error: {error}\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"\n=== Raw AI Response ===\n")
                f.write(content)
            
            print(f"  → Raw response saved to: {filepath}")
        except Exception as e:
            print(f"  → Could not save raw response: {e}")
    
    def _fallback_text_extraction(self, content: str, manuscript_id: str) -> Optional[Dict]:
        """
        Fallback: Try to extract data from malformed JSON using text parsing
        This handles cases where AI returns almost-valid JSON with minor syntax errors
        """
        try:
            import re
            
            result = {
                "dates": [],
                "locations": [],
                "persons": [],
                "colophon": None,
                "work_title": None
            }
            
            # Try to extract dates - look for patterns like "value": "1407"
            date_pattern = r'"value"\s*:\s*"(\d{4})"'
            dates_section = re.search(r'"dates"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if dates_section:
                for match in re.finditer(date_pattern, dates_section.group(1)):
                    result["dates"].append({
                        "value": match.group(1),
                        "confidence": 0.7,  # Lower confidence for fallback
                        "context": "extracted from malformed JSON"
                    })
            
            # Try to extract locations
            locations_section = re.search(r'"locations"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if locations_section:
                # Look for "value": "location_name"
                loc_pattern = r'"value"\s*:\s*"([^"]+)"'
                for match in re.finditer(loc_pattern, locations_section.group(1)):
                    location = match.group(1)
                    if location and not location.isdigit():  # Not a date
                        result["locations"].append({
                            "value": location,
                            "confidence": 0.7,
                            "context": "extracted from malformed JSON"
                        })
            
            # Try to extract persons - look for name patterns
            persons_section = re.search(r'"persons"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if persons_section:
                # Look for "name": "person_name"
                name_pattern = r'"name"\s*:\s*"([^"]+)"'
                patronymic_pattern = r'"patronymic"\s*:\s*"([^"]+)"'
                
                names = list(re.finditer(name_pattern, persons_section.group(1)))
                patronymics = list(re.finditer(patronymic_pattern, persons_section.group(1)))
                
                for i, name_match in enumerate(names):
                    person = {
                        "name": name_match.group(1),
                        "confidence": 0.7
                    }
                    # Try to match with patronymic if available
                    if i < len(patronymics):
                        person["patronymic"] = patronymics[i].group(1)
                    
                    result["persons"].append(person)
            
            # Try to extract colophon presence
            colophon_pattern = r'"colophon"\s*:\s*\{[^}]*"present"\s*:\s*(true|false)'
            colophon_match = re.search(colophon_pattern, content)
            if colophon_match:
                if colophon_match.group(1) == "true":
                    result["colophon"] = {"present": True, "text": "", "markers": []}
            
            # Try to extract work title
            work_pattern = r'"work_title"\s*:\s*\{[^}]*"title"\s*:\s*"([^"]+)"'
            work_match = re.search(work_pattern, content)
            if work_match:
                result["work_title"] = {"title": work_match.group(1), "confidence": 0.7}
            
            # Return None if nothing was extracted
            if not any([result["dates"], result["locations"], result["persons"], 
                       result["colophon"], result["work_title"]]):
                return None
            
            return result
            
        except Exception as e:
            print(f"  → Fallback extraction failed: {e}")
            return None


# ============================================================================
# CONVERSION TO DOMAIN MODELS
# ============================================================================

def ai_response_to_manuscript(
    ai_data: Dict,
    text: str,
    manuscript_id: str,
    source_metadata: Dict[str, str]
) -> Tuple[Manuscript, List]:
    """
    Convert AI extraction response to Manuscript object and ClassifiedEntity list
    
    Args:
        ai_data: AI extraction results
        text: Original manuscript notes text
        manuscript_id: Manuscript identifier
        source_metadata: Passthrough metadata
        
    Returns:
        Tuple of (Manuscript object, List of ClassifiedEntity objects)
    """
    from ..models.entities import ClassifiedEntity
    
    # List to store classified entities
    classified_entities = []
    
    # Convert dates to ExtractedEntity objects AND create ClassifiedEntity
    dates = []
    for date_data in ai_data.get("dates", []):
        if isinstance(date_data, dict) and "value" in date_data:
            entity = ExtractedEntity(
                value=str(date_data["value"]),
                entity_type=EntityType.DATE,
                confidence=float(date_data.get("confidence", 0.8)),
                context=date_data.get("context", "")
            )
            dates.append(entity)
            
            # Create ClassifiedEntity with event_type as label
            event_type = date_data.get("event_type", "unclassified")
            classified_entities.append(ClassifiedEntity(
                entity=entity,
                label=event_type,
                ontology_mapping={}  # Could add ontology mapping later
            ))
    
    # Convert locations to ExtractedEntity objects AND create ClassifiedEntity
    locations = []
    for loc_data in ai_data.get("locations", []):
        if isinstance(loc_data, dict) and "value" in loc_data:
            entity = ExtractedEntity(
                value=str(loc_data["value"]),
                entity_type=EntityType.LOCATION,
                confidence=float(loc_data.get("confidence", 0.8)),
                context=loc_data.get("context", "")
            )
            locations.append(entity)
            
            # Create ClassifiedEntity with relationship as label
            relationship = loc_data.get("relationship", "unclassified")
            classified_entities.append(ClassifiedEntity(
                entity=entity,
                label=relationship,
                ontology_mapping={}
            ))
    
    # Convert persons to Person objects
    persons = []
    for person_data in ai_data.get("persons", []):
        if isinstance(person_data, dict) and "name" in person_data:
            persons.append(Person(
                name=str(person_data["name"]),
                patronymic=person_data.get("patronymic"),
                role=person_data.get("role")
            ))
    
    # Extract colophon info
    colophon = None
    colophon_data = ai_data.get("colophon")
    if colophon_data and isinstance(colophon_data, dict):
        if colophon_data.get("present"):
            colophon = ColophonInfo(
                text=colophon_data.get("text", ""),
                has_completion_marker=True,
                scribe_name=next((p.name for p in persons if p.role == "scribe"), None)
            )
    
    # Extract work title
    work = None
    work_data = ai_data.get("work_title")
    if work_data and isinstance(work_data, dict) and work_data.get("title"):
        work = Work(title=str(work_data["title"]))
    
    manuscript = Manuscript(
        manuscript_id=manuscript_id,
        notes_text=text,
        dates=dates,
        locations=locations,
        persons=persons,
        colophon=colophon,
        work=work,
        events=[],  # Will be populated later if classification is enabled
        source_metadata=source_metadata
    )
    
    return manuscript, classified_entities


# ============================================================================
# BATCH PROCESSING
# ============================================================================

def extract_batch_with_ai(
    texts: List[Tuple[str, str, Dict]],  # (text, ms_id, metadata)
    extractor: GrokAIExtractor,
    show_progress: bool = True
) -> Tuple[List[Manuscript], Dict[str, List]]:
    """
    Extract entities from multiple texts using AI
    
    Args:
        texts: List of (text, manuscript_id, metadata) tuples
        extractor: GrokAIExtractor instance
        show_progress: Show progress bar
        
    Returns:
        Tuple of (List of Manuscript objects, Dict mapping manuscript_id to ClassifiedEntity list)
    """
    manuscripts = []
    classified_map = {}
    
    if show_progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(texts, desc="AI extraction", unit="ms")
        except ImportError:
            iterator = texts
    else:
        iterator = texts
    
    for text, ms_id, metadata in iterator:
        # Extract using AI
        ai_data = extractor.extract_from_text(text, ms_id)
        
        # Convert to Manuscript object and get classified entities
        manuscript, classified_entities = ai_response_to_manuscript(
            ai_data=ai_data,
            text=text,
            manuscript_id=ms_id,
            source_metadata=metadata
        )
        
        manuscripts.append(manuscript)
        
        # Store classified entities for this manuscript
        if classified_entities:
            classified_map[ms_id] = classified_entities
        
        # Rate limiting - small delay between requests
        time.sleep(0.2)
    
    return manuscripts, classified_map


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_ai_extractor(
    api_key: str,
    max_retries: int = 3,
    timeout: int = 45,
    fallback_dir: Optional[str] = None
) -> GrokAIExtractor:
    """
    Factory function to create AI extractor
    
    Args:
        api_key: Grok API key
        max_retries: Maximum retry attempts
        timeout: Request timeout in seconds
        fallback_dir: Directory to save raw responses when JSON parsing fails
        
    Returns:
        GrokAIExtractor instance
    """
    return GrokAIExtractor(
        api_key=api_key,
        max_retries=max_retries,
        timeout=timeout,
        fallback_dir=fallback_dir
    )

