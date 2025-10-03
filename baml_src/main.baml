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
  asserted_text string? @description("Original date text from chapter")
  parsed string? @description("Parsed date in EDTF-ish format, e.g., '1984-03~'")
  precision string? @description("Precision: year, month, day, quarter, decade")
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
  summary string @description("2-3 sentence neutral summary")
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
    8. For dates, capture the original text and attempt parsing
    9. For locations - ALWAYS extract place names mentioned in text:
       - place_name: REQUIRED - extract the location name
       - lat/lon: OPTIONAL - provide coordinates when possible:
         * If text has exact coordinates → use them, set geo_precision: "exact"
         * For well-known places (major cities, famous buildings, company headquarters) → provide approximate coordinates from your knowledge
         * Set geo_precision appropriately: "approximate-building" (for specific buildings), "approximate-city" (for cities), "approximate-region" (for regions/states)
         * For unknown/ambiguous places → leave lat/lon null
       - note: Include contextual details from the text to help with future geocoding:
         * When mentioned: year/date, specific function, named entities, size/ownership, story context
         * Preserve the location's original context from the chapter text
       - place_type: factory, headquarters, city, campus, office, lab, etc. (when evident)
    10. For people, extract names and roles when mentioned
    11. For companies, extract names and their relationship to the story
    12. For products, extract product names and details
    13. Extract themes, event_type, and tone when evident from the narrative
    14. When in doubt, prefer inclusion if the story has concrete grounding details

    Return a JSON array of Story objects matching the schema.
  "#
}
