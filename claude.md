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

## ABXGeo - Precision Geocoding (NEW)

### Overview
Separate CLI (`abxgeo`) for enhancing vague locations from ABX with precise addresses and coordinates using LLM-orchestrated web search + geocoding.

### Schema Version 1.1 (2025-10-02)
- **New columns in `story_locations`**:
  - `resolved_address` - Precise street address
  - `resolved_lat/lon` - Accurate coordinates from geocoder
  - `resolved_precision` - Level: 'address', 'street', 'city', 'region'
  - `resolution_confidence` - Score 0.0-1.0
  - `resolution_source` - JSON: {url, snippet, geocoder, is_residence}
  - `resolved_at` - Timestamp
  - `resolution_hash` - Idempotency key
  - `classifier_tier` - Classification tier: 'skip', 'simple', or 'research'
  - `classifier_reason` - Reasoning from GPT-5-mini classifier
- **New table**: `geocode_cache` - 7-day URL cache

### CLI Commands
```bash
# Setup: Configure .env file (recommended)
# Edit .env and add:
#   GOOGLE_MAPS_API_KEY=your-key-here    # 10k free calls/month
#   ABXGEO_EMAIL=your-email@example.com  # Required for Nominatim

# Migrate existing database
abxgeo migrate --db library.sqlite

# Resolve all unresolved locations (reads email from .env)
abxgeo resolve --db library.sqlite

# With custom concurrency (default: 10 workers)
abxgeo resolve --db library.sqlite --concurrency 20

# Re-resolve low-confidence locations
abxgeo resolve --db library.sqlite --incremental

# Filter by book
abxgeo resolve --db library.sqlite --book-id book_abc123

# Test with limited locations
abxgeo resolve --db library.sqlite --limit 5 --concurrency 2

# Dry run to preview
abxgeo resolve --db library.sqlite --dry-run

# Statistics (includes classifier tier distribution)
abxgeo stats --db library.sqlite

# Clear cache
abxgeo clear-cache --db library.sqlite --older-than 7d
```

### Implementation Status
**M1 Complete (2025-10-02)**:
- ✅ Schema migration (v1.0 → v1.1)
- ✅ CLI scaffold with commands: resolve, migrate, stats, clear-cache
- ✅ Test fixtures with 4 ground truth locations
- ✅ Dependencies: geopy, requests

**M2-M5 Complete (2025-10-03)**:
- ✅ M2: BAML function with OpenAI web search
  - `FindPreciseAddress`: Single-step address resolution using GPT-5 with web_search_preview tool
  - GeocodeModel client using openai-responses provider with medium reasoning effort
  - Automatic web search, extraction, and validation in one step
- ✅ M3: Removed - OpenAI web search replaces DuckDuckGo scraping
  - No longer need separate web harvester
  - OpenAI's web_search_preview tool handles all web search automatically
- ✅ M4: Geocoder cascade (Google → Nominatim fallback)
  - Primary: Google Maps (10k free calls/month, superior accuracy)
  - Fallback: Nominatim (free, OpenStreetMap-based)
  - Auto-detects GOOGLE_MAPS_API_KEY environment variable
  - Precision detection: address/street/city/region/country
  - Reverse geocoding support
- ✅ M5: Resolver orchestration + persistence
  - Simplified 3-step pipeline: BAML web search → geocoding → persistence
  - Idempotent resolution with hash-based tracking
  - Incremental mode: re-resolve low-confidence locations
  - Batch processing with progress tracking

**M6: Parallelization Complete (2025-10-03)**:
- ✅ Async/await architecture for parallel processing
  - Native async BAML calls (no asyncio.run wrapper)
  - Thread pool for blocking I/O (web search, geocoding)
  - Configurable concurrency (default: 10 workers)
- ✅ Per-service rate limiting
  - OpenAI: 10 concurrent (respects ~500 RPM limit)
  - Google Maps: 50 concurrent (10k/day, no per-second limit)
  - Nominatim: 1 req/sec (strict compliance)
- ✅ Environment variable management
  - `.env` file for API keys and email
  - `GOOGLE_MAPS_API_KEY` - Google Maps API key
  - `ABXGEO_EMAIL` - Email for Nominatim (required)
- ✅ Performance improvements
  - Sequential: ~8 hours for 479 locations
  - Parallel (10 workers): ~48 minutes
  - Parallel (20 workers): ~24 minutes

**M7: Robustness & Error Recovery (2025-10-03)**:
- ✅ **Incremental saves** - Results persisted immediately (no batch waiting)
  - Each location saved as soon as resolved
  - Progress preserved even if process interrupted
  - No data loss on partial batch failures
- ✅ **Exponential backoff retry logic**
  - 3 attempts for BAML/OpenAI calls (1s, 2s, 4s delays)
  - 2 attempts for geocoding calls (1s, 2s delays)
  - Smart detection of retryable errors (broken pipe, connection, timeout, rate limit)
- ✅ **Graceful error handling**
  - Individual failures don't crash entire batch (`return_exceptions=True`)
  - Detailed error logging in verbose mode
  - Success/fail counters track completion stats
- ✅ **Resume capability**
  - Query filters `WHERE resolved_address IS NULL`
  - Can re-run same command to resume from interruption
  - Incremental mode respects high-confidence results

**M8: Two-Tier Classifier Optimization (2025-10-03)**:
- ✅ **Problem**: First 137 locations showed 51% skip/low-value processing
  - $0.077/location cost with expensive GPT-5 web search
  - ~99s median time per location
  - Many vague country-level locations processed unnecessarily
- ✅ **Solution**: Pre-classification tier using GPT-5-mini
  - **Tier 1 - SKIP**: Vague country/region with no specific clues
    - Returns immediately with 0.2 confidence
    - No web search, no geocoding
    - Example: "China" (supplier region, no company name)
  - **Tier 2 - SIMPLE**: Well-known landmarks/HQs
    - Geocoding only (no web search)
    - High confidence (0.85)
    - Example: "Cupertino, California" → "1 Infinite Loop, Cupertino, CA 95014"
  - **Tier 3 - RESEARCH**: Specific/inferable locations
    - Full GPT-5 with web search (original expensive path)
    - Uses company context and story clues
    - Example: "Quanta factory" + Taiwan context → research tier
- ✅ **Context-aware inference**
  - Recognizes company names (Quanta, Foxconn, Pegatron)
  - Uses story context for country/region mentions
  - Considers temporal clues (year, time period)
  - Example: "Quanta factory" correctly classified as "research" when story mentions Taiwan/year
- ✅ **Expected savings**:
  - 57% cost reduction ($0.077 → $0.033/location)
  - 56% time reduction (~99s → ~44s median)
  - Based on analysis of first 137 locations (245 skippable, 67 simple, 167 research)

### Ground Truth Fixtures
1. **Fountain Factory**: "Apple factory in Fountain, Colorado" → 702 Bandley Dr, Fountain, CO 80817
2. **Crist Dr Residence**: "Patty Jobs residence, Los Altos" → 2066 Crist Dr, Los Altos, CA 94024 (residence flag)
3. **One Infinite Loop**: Apple HQ Cupertino → 1 Infinite Loop, Cupertino, CA 95014
4. **Fremont Factory**: Macintosh plant → 6400 Dumbarton Cir, Fremont, CA 94555

### File Structure
```
applebooks/
├── abx/                    # Story extraction (existing)
├── abxgeo/                 # Precision geocoding
│   ├── __init__.py
│   ├── cli.py             # CLI commands with async batch processing
│   ├── db_migrate.py      # Schema v1.0 → v1.1 migration
│   ├── resolver.py        # Core pipeline (sync + async methods)
│   ├── rate_limiter.py    # Per-service rate limiting
│   └── geocoder.py        # Google/Nominatim cascade
├── baml_src/
│   ├── main.baml          # Story extraction (ABX)
│   └── geocode.baml       # Geocoding functions (ABXGeo)
├── tests/
│   └── test_resolver.py   # Ground truth tests
├── .env                   # API keys + email (gitignored)
├── .env.example           # Template for .env
└── pyproject.toml         # Dependencies
```

## Future Improvements
- Add chunking for very long chapters (>100k tokens)
- Implement story linking via relationships field
- Add EDTF date parsing for date_start/date_end
- Create map visualization using story_locations
- Add confidence-based filtering in Datasette
- if baml file is modified, always regenerate baml code when asked to do another extraction