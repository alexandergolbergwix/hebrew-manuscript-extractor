# Hebrew Manuscript Entity Extraction System

A production-ready, ontology-driven extraction pipeline for Hebrew manuscript catalog notes, following **functional programming paradigm** and **CIDOC-CRM/LRMoo standards**.

## 🎯 Features

### Core Capabilities
- **Entity Extraction**: Dates, locations, persons, work titles, colophons
- **Kima Gazetteer Integration**: 48k+ places with Wikidata/GeoNames linking and smart false-positive filtering
- **Multi-Field Note Processing**: Combines text from MARC fields `957$a`, `500$a`, `561$a`
- **AI Classification**: Context-aware Grok API classification with 37 ontology-aligned labels
- **Event-Based Classification**: Locations classified by event type (production, transfer, residence) following CIDOC-CRM
- **Knowledge Graph**: RDF generation following CIDOC-CRM and LRMoo standards
- **Event-Centric Modeling**: All information represented as events (E12_Production, E10_Transfer, etc.)
- **Work-Expression-Manifestation Hierarchy**: Full FRBRoo/LRMoo implementation
- **Authority Enrichment**: NLI, Wikidata URI linking

### Technical Highlights
- **Functional Programming**: Pure functions, immutability, composition
- **Type-Safe**: Full type hints with dataclasses
- **Modular Architecture**: Clean separation of concerns
- **Testable**: Side effects isolated, pure logic easily testable
- **Configurable**: Single configuration object
- **Multiple Outputs**: CSV, Turtle RDF, JSON-LD

## 📁 Project Structure

```
hebrew-manuscript-extractor/
├── src/
│   ├── models/
│   │   └── entities.py          # Domain models (immutable dataclasses)
│   ├── extractors/
│   │   └── text_extractors.py   # Pure extraction functions
│   ├── classification/
│   │   └── grok_classifier.py   # AI classification (side effects isolated)
│   ├── ontology/
│   │   └── rdf_generator.py     # RDF graph generation
│   ├── io/
│   │   └── data_loader.py       # File I/O operations
│   ├── pipeline.py              # Main orchestration
│   └── __init__.py
├── tests/
│   ├── unit/                    # Unit tests for pure functions
│   └── integration/             # Integration tests
├── config/                      # Configuration files
├── data/
│   ├── input/                   # Input data files
│   └── output/                  # Generated outputs
├── main.py                      # Entry point
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or extract to your directory
cd hebrew-manuscript-extractor

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

**Set your Grok API key** (choose one method):

**Option 1: Create secrets.txt file (Recommended)**
```bash
# Copy the example file
cp secrets.txt.example secrets.txt

# Edit secrets.txt and add your API key
echo "your-grok-api-key-here" > secrets.txt
```

**Option 2: Environment variable**
```bash
export GROK_SECRET="your-grok-api-key"
```

**Option 3: Command-line argument**
```bash
python main.py --input data.xlsx --output output/ --api-key your-grok-api-key
```

**Priority Order:**
1. `--api-key` CLI argument (highest priority)
2. `secrets.txt` file in project root
3. `GROK_SECRET` environment variable (lowest priority)

### 3. Prepare Data

Place your data in `data/input/`:
- `17th_century_samples.xlsx` - Main manuscript data
- `nli_geo_subfield_z_counts_gt5.csv` - Location gazetteer (optional)

### 4. Run Extraction

**With Kima Gazetteer (Recommended for location extraction):**
```bash
python main.py --input data/input/17th_century_samples.xlsx --output output_kima/ --use-kima
```

**Standard Mode (Hybrid: Regex + AI Classification):**
```bash
python main.py --input data/input/17th_century_samples.xlsx --output data/output/
```

**AI-Only Mode (Grok extracts everything):**
```bash
python main.py --input data/input/17th_century_samples.xlsx --output data/output/ --ai-only
```

**Regex-Only Mode (No AI):**
```bash
python main.py --input data/input/17th_century_samples.xlsx --output data/output/ --no-grok
```

### 5. View Results

Check `data/output/` for:
- `manuscript_extraction_entities.csv` - Main results with extracted entities
- `manuscript_extraction_events.csv` - Structured event table
- `knowledge_graph.ttl` - RDF graph (Turtle format)
- `knowledge_graph.jsonld` - RDF graph (JSON-LD format)
- `dates_frequency.csv` - Date statistics
- `locations_frequency.csv` - Location statistics

## 🗺️ Kima Gazetteer Integration (NEW!)

### Enhanced Location Extraction

The system now integrates the **Kima/Maagarim comprehensive gazetteer** with 48,128+ historical place names, providing:

- **Wikidata & GeoNames URIs**: 70.8% of places linked to external authorities
- **Coordinates**: 76.2% of places geocoded (lat/lon)
- **Historical Hebrew Variants**: 24,980 variant forms recognized
- **Textual Forms**: 14,058 additional morphological variants

### Smart False-Positive Filtering

A sophisticated validation system eliminates common false positives:

**Problem:** Hebrew words matching obscure place names
- "נושא" (subject/topic) → "נויס (גרמניה)" (Neuss, Germany) ❌
- "ספר" (book) → "ספאר (פלורידה)" (Safar, Florida) ❌
- "אייר" (Hebrew month!) → Place names ❌

**Solution:** Multi-layer validation
1. **Blacklist pre-filter**: Blocks 61 common Hebrew words BEFORE lookup
2. **Context validation**: Requires location indicators (נכתב ב, בהיותי ב)
3. **Confidence scoring**: Tiered thresholds based on ambiguity

**Results:**
- 51% reduction in false positives (118 → 58 locations in test corpus)
- 100% elimination of major systematic errors
- Better classification variety (22% improvement)

### Usage

```bash
# Enable Kima gazetteer
python main.py --input data.xlsx --output output_kima/ --use-kima

# Test on sample
python main.py --input data.xlsx --output output_kima/ --use-kima --limit 50
```

**Output includes:**
- Canonical Hebrew place names
- Romanized names
- Wikidata/VIAF/GeoNames URIs
- Geographic coordinates
- Source confidence scores

📖 **See `KIMA_VALIDATION_FINAL_SOLUTION.md` for full technical documentation**

---

## 🎛️ Extraction Modes

The system supports **three extraction modes** to balance speed, accuracy, and API costs:

### 1. Hybrid Mode (Default) - Regex + AI Classification
```bash
python main.py --input data.xlsx --output output/
```

**How it works:**
1. **Regex patterns** extract dates, locations, persons from text (fast, deterministic)
2. **Grok AI** classifies extracted entities into ontology-aware event types (manuscript production, transfer, etc.)
3. Best balance of speed and semantic understanding

**Use when:** You want accurate extraction with contextual classification

**Pros:** Fast extraction, semantic classification, moderate API usage  
**Cons:** Regex patterns may miss complex cases

---

### 2. AI-Only Mode - Full Grok Extraction
```bash
python main.py --input data.xlsx --output output/ --ai-only
```

**How it works:**
1. **Grok AI** extracts ALL entities directly from text (no regex)
2. Returns structured JSON with dates, locations, persons, colophons, work titles
3. Includes confidence scores and surrounding context for each entity
4. Skips separate classification step (already contextually understood)

**Use when:** 
- Dealing with complex, irregular Hebrew text
- Regex patterns are too rigid
- You want maximum accuracy regardless of API costs

**Pros:** Handles complex cases, contextually aware, no pattern maintenance  
**Cons:** Slower (one API call per manuscript), higher API costs, requires API key

**Example output:**
```json
{
  "dates": [{"value": "1407", "confidence": 0.95, "context": "נכתב בשנת 1407"}],
  "locations": [{"value": "קנדיה", "confidence": 0.9, "context": "בעיר קנדיה"}],
  "persons": [{"name": "משה", "patronymic": "יצחק", "role": "scribe"}],
  "colophon": {"present": true, "text": "נשלם ביד...", "markers": ["נשלם"]},
  "work_title": {"title": "גינת אגוז", "confidence": 0.85}
}
```

---

### 3. Regex-Only Mode - No AI
```bash
python main.py --input data.xlsx --output output/ --no-grok
```

**How it works:**
1. **Regex patterns** extract entities (dates, locations, persons)
2. No AI classification - basic entity extraction only
3. No API calls required

**Use when:**
- Testing pattern accuracy
- No API key available
- Processing large datasets quickly
- Don't need semantic classification

**Pros:** Fast, free, no API dependency, deterministic  
**Cons:** No semantic understanding, basic extraction only

---

### Mode Comparison

| Feature | Regex-Only | Hybrid (Default) | AI-Only |
|---------|-----------|------------------|---------|
| **Speed** | ⚡⚡⚡ Very Fast | ⚡⚡ Fast | ⚡ Slower |
| **API Calls** | None | ~8 per ms | 1 per ms |
| **Cost** | Free | Moderate | Higher |
| **Accuracy** | Good | Very Good | Best |
| **Complex Text** | Limited | Good | Excellent |
| **Semantic Understanding** | None | Yes (classification) | Yes (extraction) |
| **API Key Required** | ❌ No | ✅ Yes | ✅ Yes |

---

### CLI Examples

**Test with limited manuscripts:**
```bash
python main.py --input data.xlsx --output output/ --limit 10
```

**AI-only with custom settings:**
```bash
python main.py --input data.xlsx --output output/ --ai-only \
  --api-key YOUR_KEY --timeout 60 --retries 5
```

**With custom gazetteer:**
```bash
python main.py --input data.xlsx --output output/ \
  --gazetteer data/locations.csv
```

**View all options:**
```bash
python main.py --help
```

---

## 📊 Output Formats

### 1. Enhanced CSV
```csv
manuscript_id,dates,locations,has_colophon,scribe_name,work_title,num_events
990001,"1407","Candia",true,"משה בן יצחק","גינת אגוז",3
```

### 2. Events CSV
```csv
manuscript_id,event_type,event_class,date,place,actor
990001,manuscript production,E12_Production,1407,Candia,משה בן יצחק
```

### 3. RDF Turtle
```turtle
@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .
@prefix lrmoo: <http://iflastandards.info/ns/lrm/lrmoo/> .

:MS_990001 a lrmoo:F4_Manifestation_Singleton ;
    crm:P1_is_identified_by "990001" ;
    hm:has_scribe :Person_Moshe_ben_Yitzhak .

:MS_990001_Production_Event a crm:E12_Production ;
    crm:P14_carried_out_by :Person_Moshe_ben_Yitzhak ;
    crm:P4_has_time_span :TimeSpan_1407 ;
    lrmoo:R27_materialized :MS_990001 .
```

## 🏗️ Architecture

### Functional Programming Principles

1. **Pure Functions**: All extraction and transformation logic is pure
   ```python
   def extract_dates(text: str) -> List[ExtractedEntity]:
       # No side effects, deterministic output
       ...
   ```

2. **Immutability**: All domain models are frozen dataclasses
   ```python
   @dataclass(frozen=True)
   class Manuscript:
       manuscript_id: str
       dates: List[ExtractedEntity]
       ...
   ```

3. **Function Composition**: Pipeline orchestrates pure transformations
   ```python
   extract → classify → create_events → build_graph → save
   ```

4. **Side Effects Isolation**: I/O and API calls isolated in specific modules
   - `io/data_loader.py` - File operations
   - `classification/grok_classifier.py` - API calls

### Module Responsibilities

| Module | Purpose | Pure? |
|--------|---------|-------|
| `models/entities.py` | Domain data structures | ✅ Pure (immutable) |
| `extractors/text_extractors.py` | Regex & Kima extraction logic | ✅ Pure functions |
| `extractors/location_validator.py` | **NEW**: False-positive filtering | ✅ Pure validation |
| `extractors/ai_extractor.py` | AI-based extraction (AI-only mode) | ⚠️ Side effects (API) |
| `classification/hebrew_patterns.py` | Event-based Hebrew patterns | ✅ Pure pattern matching |
| `classification/grok_classifier.py` | AI classification | ⚠️ Side effects (API) |
| `io/kima_loader.py` | **NEW**: Kima gazetteer loader | ⚠️ Side effects (files) |
| `ontology/rdf_generator.py` | RDF generation | ✅ Pure transformations |
| `io/data_loader.py` | File I/O | ⚠️ Side effects (files) |
| `pipeline.py` | Orchestration | ⚠️ Coordinates effects |

## 🧪 Testing

```bash
# Run unit tests (pure functions)
pytest tests/unit/ -v

# Run integration tests
pytest tests/integration/ -v

# With coverage
pytest --cov=src tests/
```

## 🔧 Configuration

### Note Fields

The system extracts from **multiple MARC note fields** and combines them:
- **957$a** - Local notes (NLI-specific)
- **500$a** - General notes
- **561$a** - Ownership and custodial history

These fields are automatically combined with ` | ` separator. To customize, edit:
```python
# In src/pipeline.py, line 272:
notes_columns=["957$a", "500$a", "561$a"]  # Modify as needed
```

### Main Configuration

Edit `main.py` or create custom config:

```python
from src.models.entities import Config

config = Config(
    input_excel_path="path/to/data.xlsx",
    output_dir="output/",
    gazetteer_path="path/to/gazetteer.csv",  # Optional
    
    # Extraction parameters
    min_token_length=2,
    max_location_tokens=6,
    
    # Grok API (optional - disable for CSV-only mode)
    use_grok=True,
    grok_api_key="your-key",
    grok_max_workers=8,
    
    # Ontology namespaces (customize if needed)
    base_namespace="http://data.hebrewmanuscripts.org/",
    hm_namespace="http://www.ontology.org.il/HebrewManuscripts/2025-08-19#",
    crm_namespace="http://www.cidoc-crm.org/cidoc-crm/",
    lrmoo_namespace="http://iflastandards.info/ns/lrm/lrmoo/",
)
```

## 📖 Usage Examples

### Basic Extraction (CSV only)

```python
from src import run_extraction_pipeline, Config

config = Config(
    input_excel_path="data.xlsx",
    output_dir="output/",
    use_grok=False  # Disable classification
)

result = run_extraction_pipeline(config)
print(result.summary)
```

### With AI Classification

```python
import os

config = Config(
    input_excel_path="data.xlsx",
    output_dir="output/",
    use_grok=True,
    grok_api_key=os.getenv("GROK_SECRET")
)

result = run_extraction_pipeline(config)
```

### Custom Processing

```python
from src.extractors.text_extractors import extract_dates, extract_colophon_info
from src.models.entities import Manuscript

text = "נשלם ביד משה בן יצחק בשנת 1407"

# Extract entities
dates = extract_dates(text)
colophon = extract_colophon_info(text)

print(f"Found {len(dates)} dates")
print(f"Is colophon: {colophon is not None}")
```

## 🎓 Ontology Compliance

### CIDOC-CRM Classes Used
- `E12_Production` - Manuscript creation events
- `E10_Transfer_of_Custody` - Ownership transfers
- `E8_Acquisition` - Purchases
- `E11_Modification` - Binding, restoration
- `E21_Person` - Scribes, authors
- `E53_Place` - Geographic locations
- `E52_Time_Span` - Temporal information

### LRMoo Hierarchy
- `F1_Work` - Abstract intellectual content
- `F2_Expression` - Specific version
- `F4_Manifestation_Singleton` - Physical manuscript
- `F32_Item_Production_Event` - Manuscript production

### Custom HM Properties
- `hm:has_scribe` - Links manuscript to scribe
- `hm:has_colophon` - Links to colophon object
- `hm:colophon_text` - Colophon text content
- `hm:external_uri_nli` - NLI authority URI

## 🔍 Advanced Features

### 1. Colophon Detection
Automatically detects colophons using 9 Hebrew patterns:
```python
COLOPHON_MARKERS = [
    r"נשלם", r"נכתב", r"וסיימתיו", r"השלמתי",
    r"תם ונשלם", r"ע\"י.*בר", ...
]
```

### 2. Scribe Name Extraction
Extracts Hebrew patronymic names:
```python
# "ביד משה בן יצחק" → Person(name="משה", patronymic="יצחק")
```

### 3. Work Title Detection
Identifies work titles from notes:
```python
# "ספר גינת אגוז" → Work(title="גינת אגוז")
```

### 4. Event Type Classification
37 ontology-aware labels:
- Work/Expression/Manuscript creation (3 levels)
- Transfer events (donation, acquisition, gift)
- Modification events (binding, restoration)
- Documentation events (cataloging, digitization)
- Person life events (birth, death)

## 📚 Dependencies

- **pandas** - Data manipulation
- **rdflib** - RDF graph generation
- **requests** - Grok API calls
- **openpyxl** - Excel file support
- **tqdm** - Progress bars (optional)

## 🤝 Contributing

This is a research project. For improvements:
1. Follow functional programming principles
2. Keep functions pure where possible
3. Add type hints
4. Write tests for new functions
5. Update documentation

## 📝 License

Academic research project - contact author for usage rights.

## 👤 Author

**Alexander Gorohovski**
- Email: alexander.gorohovski@mail.huji.ac.il
- Institution: Hebrew University of Jerusalem

## 🙏 Acknowledgments

- CIDOC-CRM Working Group
- LRMoo/FRBRoo Standards
- National Library of Israel
- Grok AI (xAI)

## 📖 Citation

If you use this system in your research, please cite:

```bibtex
@software{gorohovski2025hebrew,
  author = {Gorohovski, Alexander},
  title = {Hebrew Manuscript Entity Extraction System},
  year = {2025},
  publisher = {Hebrew University of Jerusalem},
  url = {https://github.com/...}
}
```

## 🐛 Troubleshooting

### Issue: rdflib not found
```bash
pip install rdflib
```

### Issue: Grok API errors
- Check `GROK_SECRET` is set
- Verify API key is valid
- Try reducing `grok_max_workers`

### Issue: Excel file not loading
- Ensure file is `.xlsx` format
- Check column names ("001", "500$a")
- Verify file path is correct

### Issue: No entities extracted
- Check text encoding (UTF-8)
- Verify Hebrew text is present
- Try lowering `min_token_length`

## 📬 Support

For issues, questions, or collaboration:
- Open an issue on GitHub
- Contact: alexander.gorohovski@mail.huji.ac.il

---

**Built with ❤️ for Hebrew manuscript research**
