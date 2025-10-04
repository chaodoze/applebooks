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

## Notes
- Always run `baml-cli generate` after editing BAML files
- Uses OpenAI Responses API (not Chat Completions)
- Lint before commits: `ruff check abx/ abxgeo/ --fix && ruff format abx/ abxgeo/`