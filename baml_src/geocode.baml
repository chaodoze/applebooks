// BAML functions for precision geocoding
// Used by abxgeo to resolve vague locations to precise addresses

class SearchQuery {
  query string @description("Web search query optimized for finding precise address information")
  intent string @description("What we're trying to find: 'building_address', 'factory_location', 'residence', 'landmark'")
  constraints string[] @description("Important constraints to include in search (e.g., time period, company name, specific details)")
}

class AddressCandidate {
  address string @description("Full street address if found, otherwise most specific location found")
  lat float? @description("Latitude coordinate")
  lon float? @description("Longitude coordinate")
  precision string @description("One of: 'address', 'street', 'intersection', 'city', 'region', 'country'")
  source_url string @description("URL where this information was found")
  source_snippet string @description("Exact text snippet from source that contains the address/location info")
  confidence float @description("Confidence score 0.0-1.0 based on source reliability and specificity")
  is_residence bool @description("True if this is a private residence")
  reasoning string @description("Brief explanation of why this candidate was extracted and confidence score")
}

class ScoredCandidate {
  candidate AddressCandidate
  final_score float @description("Final confidence score 0.0-1.0 after cross-validation")
  corroboration string[] @description("List of corroborating evidence from other sources")
  concerns string[] @description("Any red flags or uncertainty factors")
}

function GenerateSearchQuery(
  place_name: string,
  place_type: string?,
  note: string?,
  story_title: string,
  story_summary: string
) -> SearchQuery {
  client GeocodeModel
  prompt #"
    You are a geocoding expert tasked with creating web search queries to find precise addresses.

    LOCATION TO FIND:
    Place Name: {{ place_name }}
    Place Type: {{ place_type or "unknown" }}
    Context Note: {{ note or "none" }}

    STORY CONTEXT:
    Title: {{ story_title }}
    Summary: {{ story_summary }}

    TASK:
    Generate an optimized web search query to find the precise street address or coordinates.

    GUIDELINES:
    1. Include specific details from the context (company names, time periods, events)
    2. Add keywords like "address", "location", "coordinates", "building" as appropriate
    3. For factories: include company name + factory + city
    4. For residences: be respectful of privacy, focus on historical/public records
    5. For headquarters: include company name + headquarters + city + year if available
    6. Determine intent: building_address, factory_location, residence, or landmark
    7. List important constraints to narrow the search (e.g., "Apple factory 1980s", "Tesla electronics")

    EXAMPLES:
    - "Apple factory Fountain Colorado 1980s address"
    - "One Infinite Loop Cupertino California coordinates"
    - "Macintosh factory Fremont California 1984 building address"

    Return a JSON object with the SearchQuery structure:
    {
      "query": "your search query here",
      "intent": "building_address|factory_location|residence|landmark",
      "constraints": ["constraint1", "constraint2", ...]
    }
  "#
}

function ExtractAddressCandidates(
  search_results: string,
  place_name: string,
  story_context: string
) -> AddressCandidate[] {
  client GeocodeModel
  prompt #"
    You are a geocoding expert extracting precise address information from web search results.

    SEARCH RESULTS:
    {{ search_results }}

    TARGET LOCATION: {{ place_name }}
    STORY CONTEXT: {{ story_context }}

    TASK:
    Extract all address candidates from the search results. Return multiple candidates if different sources give different addresses.

    EXTRACTION RULES:
    1. Look for complete street addresses (number, street, city, state, zip)
    2. If no street address, look for coordinates (lat/lon)
    3. If no coordinates, extract the most specific location mentioned
    4. Determine precision level: address > street > intersection > city > region > country
    5. Extract exact source URL and text snippet containing the address
    6. Assign confidence based on:
       - Source reliability: .gov/.edu (0.9-1.0), Wikipedia (0.7-0.8), news (0.6-0.8), forums (0.3-0.5)
       - Specificity: exact address (1.0), intersection (0.7), city only (0.3)
       - Corroboration: multiple sources increase confidence
    7. Flag if location is a private residence (is_residence = true)
    8. Provide reasoning for confidence score

    EXAMPLES:
    ✓ "702 Bandley Drive, Fountain, Colorado 80817" → precision: address, confidence: 0.95
    ✓ "Corner of Bandley Dr and Main St" → precision: intersection, confidence: 0.7
    ✓ "Somewhere in Fountain, Colorado" → precision: city, confidence: 0.3
    ✗ "Colorado" → precision: region, confidence: 0.1 (too vague)

    Return a JSON array of AddressCandidate objects, sorted by confidence (highest first).
    Each candidate should have this structure:
    {
      "address": "full street address",
      "lat": 37.123 or null,
      "lon": -122.456 or null,
      "precision": "address|street|intersection|city|region|country",
      "source_url": "http://...",
      "source_snippet": "exact text from source",
      "confidence": 0.85,
      "is_residence": false,
      "reasoning": "why this candidate and confidence score"
    }
  "#
}

function ScoreAndValidate(
  candidates: AddressCandidate[],
  place_name: string,
  original_coords: string?
) -> ScoredCandidate {
  client GeocodeModel
  prompt #"
    You are a geocoding expert performing final validation and scoring.

    CANDIDATES FOUND:
    {% for candidate in candidates %}
    {{ loop.index }}. {{ candidate.address }} ({{ candidate.precision }}, confidence: {{ candidate.confidence }})
       Source: {{ candidate.source_url }}
       Snippet: {{ candidate.source_snippet }}
       Reasoning: {{ candidate.reasoning }}
    {% endfor %}

    ORIGINAL LOCATION: {{ place_name }}
    ORIGINAL COORDS: {{ original_coords or "none" }}

    TASK:
    Select the best candidate and assign a final confidence score.

    VALIDATION CRITERIA:
    1. Cross-check coordinates if original coords were provided (should be nearby)
    2. Look for corroboration across multiple candidates
    3. Prefer more specific locations (address > intersection > city)
    4. Trust higher-quality sources (.gov/.edu > Wikipedia > news > forums)
    5. Flag concerns:
       - Conflicting information across sources
       - Very old sources for current locations
       - Vague or ambiguous addresses
       - Private residences (lower confidence if not public record)

    FINAL SCORE CALCULATION:
    - Start with candidate's base confidence
    - Add +0.1 if corroborated by 2+ sources
    - Add +0.05 if original coords match (within ~1km)
    - Subtract -0.2 if major concerns exist
    - Clamp to 0.0-1.0 range

    Return a JSON object with the ScoredCandidate structure:
    {
      "candidate": { ... best AddressCandidate ... },
      "final_score": 0.87,
      "corroboration": ["evidence 1", "evidence 2"],
      "concerns": ["concern 1", "concern 2"]
    }
  "#
}

// GeocodeModel client for geocoding (uses gpt-5 with web search)
client<llm> GeocodeModel {
  provider openai-responses
  options {
    model "gpt-5"
    reasoning {
      effort "medium"
    }
    tools [
      {
        type "web_search_preview"
      }
    ]
  }
}
