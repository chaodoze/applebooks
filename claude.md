# ABX - Apple Books Extraction System

## Overview
LLM-powered story extraction from EPUBs using BAML + OpenAI GPT-5.

## Architecture
```
EPUB → Chapterizer → Cleaner → BAML (GPT-5) → SQLite (FTS) → Datasette
```

## CLI
```bash
# Story extraction
abx extract --epub <path> --db <path> --schema ./schema/story.schema.json --batch --verbose

# Geocoding (two-tier classifier: skip/simple/research)
abxgeo resolve --db <path> --concurrency 10

# Stats
abxgeo stats --db <path>
```

## Key Files
- `baml_src/main.baml` - Story extraction schema (run `baml-cli generate` after editing)
- `baml_src/geocode.baml` - Geocoding with OpenAI web search
- `schema/story.schema.json` - Story schema (entities: people, companies, products, locations)
- `.env` - API keys: `OPENAI_API_KEY`, `GOOGLE_MAPS_API_KEY`, `ABXGEO_EMAIL`

## Models
- **ABX**: GPT-5 with `reasoning_effort: medium` ($1.25/1M in, $10/1M out)
- **ABXGeo Classifier**: GPT-5-mini ($0.25/1M in, $2/1M out)
- **ABXGeo Research**: GPT-5 with web search

## Database Schema
- `stories` - Extracted stories with FTS5
- `story_locations` - Locations with resolved addresses (schema v1.1)
  - `resolved_address`, `resolved_lat/lon`, `resolved_precision`
  - `classifier_tier` (skip/simple/research), `resolution_confidence`
- `geocode_cache` - 7-day URL cache

## ABXGeo Two-Tier Classifier
- **Tier 1 - SKIP**: Vague country/region → 0.2 confidence, no processing
- **Tier 2 - SIMPLE**: Well-known landmarks → geocoding only, 0.85 confidence
- **Tier 3 - RESEARCH**: Specific locations → GPT-5 web search + geocoding

Performance: 57% cost reduction, 56% time reduction vs naive approach.

## Common Commands
```bash
# Setup
pip install -e .
baml-cli generate

# Extraction
abx extract --epub book.epub --db library.sqlite --schema ./schema/story.schema.json --batch

# Geocoding
abxgeo migrate --db library.sqlite  # One-time schema upgrade
abxgeo resolve --db library.sqlite --concurrency 10

# Analysis
datasette library.sqlite -m datasette_metadata.json --port 8001
```

## Prompt Engineering Learnings (Oct 2025)

### Story Summaries - Map-Worthy Excerpts
**Problem**: Original summaries were dry, archival, inconsistent length (84-575 chars)
**Solution**: Rewrote prompt to create compelling map pin excerpts
- Target: 200-350 chars with drama/conflict/scale front-loaded
- Include vivid details: quotes, numbers, sensory descriptions
- Provide context for readers who skimmed the book
- Show stakes and significance

**Results**:
- Old: "Apple's iPad name dispute with Proview Technology in China" (84 chars)
- New: "Apple paid $60 million to settle after Chinese courts ruled Shenzhen-based Proview had registered 'iPad' in 2000, threatening tablet sales across China" (241 chars)
- Consistency: All summaries now 241-293 chars ✅

### Date Extraction - ISO 8601 EDTF with Examples
**Problem**: `asserted_text` NEVER populated (0/388 stories), weak EDTF compliance
**Solution**: Added explicit IF/THEN logic + 9 concrete examples in prompt
- IF date in text: capture asserted_text + parsed + precision (all required)
- IF no date: set to null (don't hallucinate)
- "Rough timeframes better than nothing" (e.g., "early 2000s")
- Concrete examples: "March 15, 2013" → `{asserted_text: "March 15, 2013", parsed: "2013-03-15", precision: "day"}`

**Results**:
- Old: 0/388 had asserted_text, weak EDTF
- New: 8/9 have full date objects with proper EDTF ✅
- Model even calculates relative dates: "Eighteen days after CCTV" → "2013-04-02" ✅

### Location Notes - Geocoding Context
**Problem**: Generic notes like "Apple's home base"
**Solution**: Explicit examples of rich contextual details
- Temporal markers: "(1984-1996, closed due to...)"
- Functional details: "340k sq ft, 27-sec cycle time"
- Named entities, scale, story significance

**Key Insight**: LLMs need explicit examples, not just descriptions. Show, don't tell.

## Notes
- Always run `baml-cli generate` after editing BAML files
- Uses OpenAI Responses API (not Chat Completions)
- Lint before commits: `ruff check abx/ abxgeo/ --fix && ruff format abx/ abxgeo/`
- When prompting GPT-5: Add 5-10 concrete examples for complex formats (EDTF, structured data)