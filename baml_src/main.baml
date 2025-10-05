// BAML configuration for story extraction

client<llm> GPT4o {
  provider openai
  options {
    model "gpt-4o-2024-08-06"
    api_key env.OPENAI_API_KEY
    temperature 0
  }
}

client<llm> GPT4oMini {
  provider openai
  options {
    model "gpt-4o-mini"
    api_key env.OPENAI_API_KEY
    temperature 0
  }
}

// Auto-resolve to best available model (GPT-5)
client<llm> AutoModel {
  provider openai
  options {
    model "gpt-5"
    api_key env.OPENAI_API_KEY
    reasoning_effort "medium"
  }
}

class DateInfo {
  asserted_text string? @description("ALWAYS capture original date text verbatim from chapter, e.g., 'spring 1984', 'early 1980s', 'March 1996'")
  parsed string? @description("Parse to ISO 8601 EDTF format: '1984-03~' (approx), '1984?' (uncertain), '1984-03/1984-06' (range), '198X' (1980s), '1984-XX' (sometime in 1984)")
  precision string? @description("Auto-filled from parsed format: 'day', 'month', 'year', 'decade', 'range'")
}

class Location {
  place_name string @description("Name of the place")
  lat float? @description("Latitude")
  lon float? @description("Longitude")
  place_type string? @description("Type of place: office, lab, factory, etc.")
  geo_precision string? @description("building, campus, city, region")
  visitability string? @description("public, private, historical")
  note string? @description("Additional context")
}

class Person {
  name string @description("Person's name")
  role_at_time string? @description("Role at the time of the story")
  team string? @description("Team or department")
  affiliation string? @description("Company or organization")
}

class Product {
  product_line string? @description("Product line")
  model string? @description("Model name or number")
  codename string? @description("Internal codename")
  generation string? @description("Generation or version")
  design_language string? @description("Design language or style")
}

class Company {
  name string @description("Company name")
  relationship string? @description("Relationship to the story: beneficiary, competitor, partner, etc.")
}

class Provenance {
  source_type string @description("Type of source: book, interview, memo, etc.")
  citation string? @description("Citation text")
  isbn string? @description("ISBN if book source")
  author string? @description("Author of source")
  pub_year int? @description("Publication year")
  quote_snippet string? @description("Direct quote from source")
}

class Relationships {
  contradicts string[]? @description("Story IDs this contradicts")
  references string[]? @description("Story IDs this references")
  precedes string[]? @description("Story IDs this precedes")
}

class Media {
  asset_type string @description("Type: photo, video, document, etc.")
  uri string? @description("URI to the asset")
  credit string? @description("Credit/attribution")
  license string? @description("License type")
  date string? @description("Date of asset")
}

class Story {
  story_id string @description("Use 'auto_or_uuid' to auto-generate")
  title string @description("Short descriptive title")
  summary string @description("Compelling 200-350 char story excerpt for map pins. Front-load drama/conflict/scale. Include vivid details (quotes, numbers, sensory descriptions). Assume reader skimmed book - provide context.")
  dates DateInfo? @description("Date information")
  locations Location[]? @description("Locations mentioned in the story")
  forward_locale Location? @description("Forward-looking location where impact occurred")
  people Person[]? @description("People involved")
  products Product[]? @description("Products mentioned")
  companies Company[]? @description("Companies involved")
  event_type string[]? @description("Event types: DesignDecision, Prototype, ProductLaunch, etc.")
  themes string[]? @description("Themes: innovation, conflict, partnership, etc.")
  tone string[]? @description("Tone: triumphant, tense, nostalgic, etc.")
  business_phase string? @description("Business phase or era")
  era string? @description("Era description")
  relationships Relationships? @description("Relationships to other stories")
  provenance Provenance[]? @description("Source citations")
  confidence float @description("Confidence score 0-1")
  freeform_tags string[]? @description("Freeform tags")
  media Media[]? @description("Media assets")
}

function ExtractStories(chapter_text: string, book_context: string) -> Story[] {
  client AutoModel
  prompt #"
    You are extracting structured stories from a chapter of a book about Apple Computer history.

    Book context: {{ book_context }}

    Chapter text:
    ---
    {{ chapter_text }}
    ---

    Instructions:
    1. Extract 0 or more Story objects from this chapter
    2. Focus on SPECIFIC, CONCRETE stories rather than general summaries:
       - Extract stories about particular incidents, events, decisions, or actions
       - Look for grounding details: named people, specific numbers, locations, dates, quotes
       - A story should have narrative specificity, not just list facts or trends

       ❌ Skip only:
          - Pure background or context paragraphs without a specific event
          - Multi-year trend summaries without concrete incidents
          - Abstract lists of challenges or factors

       ✅ Good story markers (include a good strong marker or if story has a few):
          - Named individuals taking action or making decisions (especially main characters like Jobs, Cook, Wozniak, Sculley etc.)
          - Specific amounts, dates, or quantities (e.g., "50,000 units", "March 1984")
          - Identifiable places or facilities (e.g., "Cupertino factory", "Bandley Drive")
          - Clear cause-and-effect or turning points
          - Direct quotes or specific conflicts between people/companies
          - Concrete products, prototypes, or technical decisions
    3. Each story must be grounded in the chapter text - no external knowledge
    4. Use "auto_or_uuid" for story_id to auto-generate
    5. Include provenance when available
    6. Assign confidence based on narrative detail and specificity (range: 0.5-0.8 is typical)
    7. Extract only factual information, not speculation
    8. For SUMMARIES - write compelling story excerpts for map pins (200-350 chars):
       - Front-load the most dramatic/interesting element: conflict, surprise, scale, stakes
       - Include vivid details: specific numbers, direct quotes, sensory descriptions
       - Provide context for readers who only skimmed the book - explain significance
       - Show what was at risk or why this moment mattered
       - Examples of transformation:
         * Weak: "Apple had a trademark dispute in China"
         * Strong: "Apple paid $60 million to settle after Chinese courts ruled Shenzhen-based Proview had registered 'iPad' in 2000, threatening tablet sales across China"
    9. For DATES - extract if present in text (don't hallucinate):
       - IF a date/timeframe is mentioned in the chapter text:
         * asserted_text: REQUIRED - capture the exact original phrase verbatim
         * parsed: REQUIRED - convert to ISO 8601 EDTF format
         * precision: REQUIRED - specify granularity
       - Rough timeframes are better than nothing (e.g., "early 2000s", "following year")
       - IF no date/timeframe in text: set dates to null (don't guess or infer)

       EDTF format examples:
       * "March 15, 2013" → asserted_text: "March 15, 2013", parsed: "2013-03-15", precision: "day"
       * "spring 1984" → asserted_text: "spring 1984", parsed: "1984-03/1984-06", precision: "range"
       * "early 1980s" → asserted_text: "early 1980s", parsed: "1981/1985", precision: "range"
       * "late March 1996" → asserted_text: "late March 1996", parsed: "1996-03~", precision: "month"
       * "summer of 1997" → asserted_text: "summer of 1997", parsed: "1997-06/1997-09", precision: "range"
       * "1984" → asserted_text: "1984", parsed: "1984", precision: "year"
       * "1980s" → asserted_text: "1980s", parsed: "198X", precision: "decade"
       * "around 2015" → asserted_text: "around 2015", parsed: "2015~", precision: "year"
       * "possibly 1984" → asserted_text: "possibly 1984", parsed: "1984?", precision: "year"
    10. For LOCATIONS - capture rich contextual notes for geocoding:
       - place_name: REQUIRED - extract the location name
       - lat/lon: OPTIONAL - provide coordinates when possible:
         * If text has exact coordinates → use them, set geo_precision: "exact"
         * For well-known places (major cities, famous buildings, company headquarters) → provide approximate coordinates from your knowledge
         * Set geo_precision appropriately: "approximate-building" (for specific buildings), "approximate-city" (for cities), "approximate-region" (for regions/states)
         * For unknown/ambiguous places → leave lat/lon null
       - note: Include rich contextual details from text to assist future precise geocoding:
         * Temporal markers: "Fremont factory (1984-1996, closed due to Mac sales collapse)"
         * Functional details: "340,000 sq ft Macintosh assembly plant, 27-second cycle time"
         * Named entities: "Acquired by SCI Systems for ~$200M in March 1996"
         * Scale/ownership: "Apple's $20M state-of-the-art factory"
         * Story significance: Why this location matters to the narrative
         * Example: "Foxconn Longhua facility, Shenzhen (2010-present). 230k workers, iPhone assembly. Site of 2010 worker suicides."
       - place_type: factory, headquarters, city, campus, office, lab, etc. (when evident)
    11. For people, extract names and roles when mentioned
    12. For companies, extract names and their relationship to the story
    13. For products, extract product names and details
    14. Extract themes, event_type, and tone when evident from the narrative
    15. When in doubt, prefer inclusion if the story has concrete grounding details

    Return a JSON array of Story objects matching the schema.
  "#
}
