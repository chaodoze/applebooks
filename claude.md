# ABX - Apple Books Extraction System

## Overview
LLM-powered story extraction from Apple history EPUBs using BAML + OpenAI GPT-5 with structured outputs.

## Architecture
```
EPUB → Chapterizer → Cleaner → BAML (GPT-5, reasoning_effort: high)
     → Stories JSON → SQLite (FTS) → Datasette
```

## Key Components

### 1. EPUB Processing (`abx/epub_parser.py`, `abx/cleaner.py`)
- Intelligent chaptering: nav/TOC → spine → h1/h2 fallback
- HTML cleaning: loose (default) or strict modes
- Stores both raw and cleaned text for FTS

### 2. LLM Integration (`abx/llm.py`, `baml_src/main.baml`)
- **Model**: GPT-5 with `reasoning_effort: "high"` (default)
- **Modes**: Batch (default, 50% cheaper) or sync
- **BAML client**: Must be at project root, regenerate after schema changes: `baml-cli generate`
- Token estimation and safety checks included

### 3. Story Schema (`schema/story.schema.json`)
- **Required**: `story_id`, `title`, `summary`
- **Entities**: people, companies, products, locations
- **Metadata**: dates, themes, tone, confidence, provenance
- **Special**: `forward_locale` for impact locations

#### Location Extraction Strategy
- **Phase 4 (Current)**: GPT-5 extracts approximate coordinates from knowledge
  - `place_name`: REQUIRED - always extract location names
  - `lat`/`lon`: OPTIONAL - approximate coords for well-known places
  - `geo_precision`: "exact", "approximate-building", "approximate-city", "approximate-region", or null
  - `note`: REQUIRED - preserves original text context for future geocoding
  - Example: "Cupertino" → lat: 37.323, lon: -122.032, precision: "approximate-city", note: "Cupertino, California"
- **Phase 2 (Future)**: Post-processing with GeoPy + Nominatim for precise coordinates
- **Phase 3 (Future)**: Real-time function calling during extraction

### 4. Database (`abx/db.py`, `abx/persistence.py`)
- SQLite with FTS5 on chapters and stories
- Pivot tables: story_people, story_companies, story_products, story_locations
- Idempotency: `(book_sha, schema_version, model, prompt_hash)`

### 5. CLI (`abx/cli.py`)
```bash
abx extract \
  --epub <path> \
  --db <path> \
  --schema ./schema/story.schema.json \
  --model auto \
  --batch \
  --clean-html loose \
  --verbose
```

## Model Configuration

### Current Default
- **Model**: `gpt-5` with `reasoning_effort: "medium"`
- **Benefits**: 45% fewer errors vs GPT-4o, 80% fewer vs o3
- **Cost**: $1.25/1M input, $10/1M output tokens
- **Performance**: Balanced speed and quality (changed from "high" due to long processing times)

### Alternatives
- `gpt-5-mini`: $0.25/1M input, $2/1M output
- `gpt-5-nano`: $0.05/1M input, $0.40/1M output
- Legacy: `gpt-4o-2024-08-06`

### Reasoning Effort
- `high` - Maximum quality, extended reasoning (6+ min per chapter)
- `medium` ✅ - Balanced speed and quality (default)
- `low` - Faster responses
- `minimal` - Fastest time-to-first-token

## Development Workflow

### Setup
```bash
pip install -e .
export OPENAI_API_KEY="sk-..."
baml-cli generate
```

### Making Changes

**1. Update BAML schema** (`baml_src/main.baml`)
```bash
# After editing
baml-cli generate
```

**2. Update Story schema** (`schema/story.schema.json`)
```bash
# Update JSON schema
# Update persistence.py to handle new fields
# Run: baml-cli generate
```

**3. Change default model**
- Edit `baml_src/main.baml` → AutoModel client
- Edit `abx/llm.py` → `resolve_model()` function
- Edit `abx/llm.py` → `prepare_batch_input()` model name
- Regenerate: `baml-cli generate`

### Testing
```bash
# Quick test (3 chapters, sync mode)
abx extract --epub test.epub --db test.sqlite --schema ./schema/story.schema.json --sync --chapter-limit 3 --verbose

# Full extraction (batch mode)
abx extract --epub book.epub --db library.sqlite --schema ./schema/story.schema.json --batch --verbose

# Explore results
datasette library.sqlite -m datasette_metadata.json --port 8001
```

### Linting
```bash
ruff check abx/ --fix
ruff format abx/
```

## Common Issues

### BAML Import Errors
- Ensure `baml_client/` is at project root
- Check `abx/llm.py` adds project root to sys.path
- Regenerate: `baml-cli generate`

### Idempotency Skipping Runs
- Change triggers: book content, schema version, model name, or prompt
- Delete run from `llm_runs` table to force re-run
- Or use different model: `--model gpt-5-mini`

### XML Parsing Warnings
- Expected for EPUB XHTML content
- BeautifulSoup uses lxml parser (correct)
- Warnings are cosmetic, can be filtered

### None Values in Stories
- GPT-5 returns None for optional fields when data not present
- `persistence.py` handles with `or []` for arrays
- This is correct behavior for sparse data

## File Structure
```
applebooks/
├── abx/                    # Main package
│   ├── cli.py             # Click CLI with rich progress
│   ├── db.py              # SQLite schema + FTS
│   ├── epub_parser.py     # EPUB → chapters
│   ├── cleaner.py         # HTML → clean text
│   ├── llm.py             # BAML + OpenAI integration
│   └── persistence.py     # Story → SQLite
├── baml_src/
│   └── main.baml          # BAML schema (EDIT THIS)
├── baml_client/           # Generated (DO NOT EDIT)
├── schema/
│   └── story.schema.json  # JSON Schema (EDIT THIS)
├── datasette_metadata.json # Datasette config
├── pyproject.toml         # Dependencies
└── README.md              # User documentation
```

## Production Deployment

### Full Book Extraction
```bash
# Batch mode (recommended)
abx extract \
  --epub "Apple in China.epub" \
  --db library.sqlite \
  --schema ./schema/story.schema.json \
  --model auto \
  --batch \
  --verbose

# Expect: ~1-2 hours for batch job to complete
# Cost: ~$50-100 for 400-page book with GPT-5
```

### Monitoring
- Check `llm_runs` table for run status
- Monitor `chapter_llm` for per-chapter errors
- Query `stories` table for extraction counts
- Use Datasette for data quality validation

### Data Quality Checks
```sql
-- Stories per chapter
SELECT book_id, COUNT(*) FROM stories GROUP BY book_id;

-- Confidence distribution
SELECT ROUND(confidence*10)/10.0 AS bucket, COUNT(*)
FROM stories GROUP BY bucket ORDER BY bucket;

-- Entity coverage
SELECT
  COUNT(*) AS total_stories,
  SUM(CASE WHEN people IS NOT NULL THEN 1 ELSE 0 END) AS with_people,
  SUM(CASE WHEN companies IS NOT NULL THEN 1 ELSE 0 END) AS with_companies
FROM stories;
```

## Recent Changes

### Location Extraction (Phase 4) - 2025-09-29
- **Problem**: Locations were being extracted but with empty arrays because prompt required coordinates
- **Solution**: Made coordinates truly optional while allowing approximate values
  - Updated `schema/story.schema.json` with detailed field descriptions
  - Enhanced BAML prompt instructions for location extraction (baml_src/main.baml:132-150)
  - GPT-5 now provides approximate coordinates from knowledge when appropriate
  - `note` field preserves context for future precise geocoding
- **Results**: 36 locations extracted from 5 chapters (previously 0)
  - 33 with approximate coordinates (91.7%)
  - 3 correctly left null for ambiguous places
  - Precision tracking: city, country, region, building levels

### Reasoning Effort Change - 2025-09-29
- **Problem**: `reasoning_effort: "high"` caused very long processing times (6+ min per chapter)
- **Solution**: Changed default to `reasoning_effort: "medium"` for better balance
  - Sync mode extractions now complete faster
  - Still maintains high quality extraction
  - Users can override with custom client config if needed

## Future Improvements
- Add chunking for very long chapters (>100k tokens)
- Implement story linking via relationships field
- Add EDTF date parsing for date_start/date_end
- Create map visualization using story_locations
- Add confidence-based filtering in Datasette
- Phase 2 geocoding: Post-process locations with GeoPy + Nominatim
- Phase 3 geocoding: Real-time function calling during extraction