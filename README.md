# ABX - Apple Books EPUB Extraction

Extract structured stories from Apple history books using LLM-powered analysis with OpenAI's Responses API and BAML.

## Features

- **EPUB parsing**: Intelligent chaptering with automatic title extraction
- **HTML cleaning**: Configurable loose/strict modes
- **LLM extraction**: Story extraction via BAML + OpenAI Responses API (structured outputs)
- **Batch processing**: Default batch mode with job polling for cost efficiency
- **SQLite storage**: Full-text search enabled, deterministic storage
- **Idempotency**: Re-runs detect existing work via (book_sha, schema_version, model, prompt_hash)
- **Rich CLI**: Progress bars, colored output, comprehensive logging
- **Datasette integration**: Explore extracted stories with pre-configured queries and facets

## Installation

```bash
# Clone the repository
cd applebooks

# Install with pip (development mode)
pip install -e .

# Or install with dependencies
pip install -e ".[dev]"
```

## Setup

### 1. Set OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

### 2. Initialize BAML

```bash
# Install BAML CLI if not already installed
npm install -g @boundaryml/baml

# Generate BAML client
cd applebooks
baml-cli generate
```

## Usage

### Basic extraction

```bash
abx extract \
  --epub ~/books/PrideAndPrejudice.epub \
  --db ~/abx/library.sqlite \
  --schema ./schema/story.schema.json \
  --model auto \
  --batch \
  --clean-html loose \
  --verbose
```

### Command-line options

```
Options:
  --epub PATH              Path to EPUB file [required]
  --db PATH                Path to SQLite database [required]
  --schema PATH            Path to story JSON schema [required]
  --model TEXT             Model name (auto = best available) [default: auto]
  --batch / --no-batch     Use batch mode [default: batch]
  --sync                   Force synchronous mode
  --parallel INTEGER       Parallel workers for local processing [default: 4]
  --clean-html [loose|strict]
                           HTML cleaning mode [default: loose]
  --chapter-limit INTEGER  Max chapters to process [default: 999]
  --retry INTEGER          LLM retry attempts [default: 3]
  --max-input-tokens INTEGER
                           Max input tokens (0 = no limit) [default: 0]
  --fail-on-warnings       Treat warnings as fatal
  --verbose                Verbose output
  --help                   Show this message and exit
```

### Model selection

- `auto` (default): Resolves to best available OpenAI model (currently `gpt-5` with `reasoning_effort: high`)
- Explicit model name: e.g., `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4o-2024-08-06`

**GPT-5 Reasoning Models:**
- GPT-5 uses advanced reasoning with configurable effort levels: `minimal`, `low`, `medium`, `high`
- `high` (default): Maximum quality with extended reasoning for thorough analysis
- `minimal`: Fastest time-to-first-token for quick responses

### Batch vs. Sync mode

**Batch mode (default)**:
- More cost-effective (50% discount)
- Asynchronous processing with job polling
- Best for large books

**Sync mode** (`--sync`):
- Real-time processing
- Immediate results
- Best for testing or small books

### Idempotency

Re-running the same extraction with identical parameters (book_sha, schema_version, model, prompt_hash) will skip processing:

```bash
abx extract --epub ~/books/SameBook.epub --db library.sqlite --schema schema/story.schema.json
# First run: processes all chapters
# Second run: skips (idempotent)
```

## Exploring results with Datasette

```bash
# Install Datasette
pip install datasette datasette-cluster-map

# Launch
datasette library.sqlite -m datasette_metadata.json --setting default_facet_size 25

# Open in browser
open http://127.0.0.1:8001
```

### Recommended queries

Pre-configured queries in `datasette_metadata.json`:

- **Stories per chapter**: Distribution of stories across chapters
- **People leaderboard**: Most mentioned people
- **Event type distribution**: Breakdown of event types
- **Theme/tone distribution**: Analysis of themes and tones
- **Map candidates**: Stories with geographic coordinates
- **Confidence buckets**: Distribution of confidence scores
- **Company relationships**: Companies and their relationships
- **Product generations**: Product lines and generations
- **Usage summary**: LLM token usage and timing

## Database schema

### Core tables

- `books`: Book metadata (title, authors, SHA256, etc.)
- `chapters`: Chapters with raw and cleaned text (FTS-enabled)
- `stories`: Extracted stories with indexed fields (FTS-enabled)

### Pivot tables

- `story_people`: People mentioned in stories
- `story_companies`: Companies involved
- `story_products`: Products referenced
- `story_locations`: Locations (including forward_locale)

### Metadata tables

- `llm_runs`: LLM run metadata (model, prompt_hash, batch_job_id)
- `chapter_llm`: Per-chapter LLM results (tokens, duration, errors)

## Story schema

See `schema/story.schema.json` for the complete JSON Schema.

Key fields:
- `story_id`: Auto-generated or provided
- `title`: Short descriptive title
- `summary`: 2-3 sentence summary
- `dates`: Date information (original text + parsed)
- `locations`: Places mentioned
- `forward_locale`: Forward-looking location where impact occurred
- `people`, `products`, `companies`: Entity extraction
- `event_type`, `themes`, `tone`: Classification
- `provenance`: Source citations
- `confidence`: 0-1 confidence score

## Exit codes

- `0`: Success
- `1`: Partial success with warnings
- `2`: Fatal error

## Development

### Run linting

```bash
ruff check .
ruff format .
```

### Run tests

```bash
pytest
```

## Troubleshooting

### BAML not found

Make sure BAML is installed and generated:

```bash
npm install -g @boundaryml/baml
baml-cli generate
```

### OpenAI API errors

Check your API key:

```bash
echo $OPENAI_API_KEY
```

Verify you have access to the model:

```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### SQLite locked

Ensure no other process is accessing the database:

```bash
lsof library.sqlite
```

## Architecture

```
EPUB → Chapterizer → Cleaner
     → BAML (OpenAI Responses API, structured outputs)
     → [Story...] JSON
     → SQLite (books, chapters, stories, pivots, runs, usage)
     → Datasette
```

## License

MIT