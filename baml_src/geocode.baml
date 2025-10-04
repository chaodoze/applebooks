// BAML functions for precision geocoding
// Used by abxgeo to resolve vague locations to precise addresses

class LocationClassification {
  category string @description("One of: 'skip', 'simple', 'research'")
  reason string @description("Why this category was chosen")
  simple_address string? @description("If category is 'simple', provide the well-known address (e.g., '1 Infinite Loop, Cupertino, CA')")
  estimated_precision string? @description("If category is 'simple', estimated precision: 'address', 'city', etc.")
}

class AddressResolution {
  address string @description("Full street address if found, otherwise most specific location found")
  lat float? @description("Latitude coordinate")
  lon float? @description("Longitude coordinate")
  precision string @description("One of: 'address', 'street', 'intersection', 'city', 'region', 'country'")
  source_url string @description("URL where this information was found")
  source_snippet string @description("Exact text snippet from source that contains the address/location info")
  confidence float @description("Confidence score 0.0-1.0 based on source reliability and specificity")
  is_residence bool @description("True if this is a private residence")
  corroboration string[] @description("List of corroborating evidence from other sources")
  concerns string[] @description("Any red flags or uncertainty factors")
  reasoning string @description("Brief explanation of how address was found and confidence score")
}

function FindPreciseAddress(
  place_name: string,
  place_type: string?,
  note: string?,
  story_title: string,
  story_summary: string,
  original_lat: float?,
  original_lon: float?
) -> AddressResolution {
  client GeocodeModel
  prompt #"
    You are a geocoding expert tasked with finding the precise street address for a location.

    IMPORTANT: You have access to web search. USE IT to find authoritative sources with precise addresses.
    Search multiple sources if needed to corroborate information.

    LOCATION TO FIND:
    Place Name: {{ place_name }}
    Place Type: {{ place_type or "unknown" }}
    Context Note: {{ note or "none" }}
    Original Coordinates: {% if original_lat and original_lon %}{{ original_lat }}, {{ original_lon }}{% else %}none{% endif %}

    STORY CONTEXT:
    Title: {{ story_title }}
    Summary: {{ story_summary }}

    TASK:
    Use web search to find the precise street address and coordinates for this location.

    IMPORTANT - HANDLING VAGUE LOCATIONS:
    - If the location is too vague (e.g., "United States", "California", "Asia") WITHOUT sufficient context to identify a specific building/address, DO NOT try to force a street address
    - For vague country/region references, return just the country/region name with low confidence (0.1-0.3)
    - Set precision to "country" or "region" accordingly
    - In the "concerns" field, note: "Location too vague - insufficient context for specific address"
    - ONLY search for specific addresses if there are clear clues (company name, factory, headquarters, landmark, event, etc.)

    SEARCH STRATEGY (only if location is specific enough):
    1. For factories: search "company name + factory + city + address"
    2. For headquarters: search "company name + headquarters + city + year + address"
    3. For residences: be respectful of privacy, focus on historical/public records
    4. For landmarks: search "landmark name + city + address"
    5. Include time period context if mentioned (e.g., "1980s", "1984")
    6. For vague references: accept the vagueness, don't force a search

    EXTRACTION RULES:
    1. Look for complete street addresses (number, street, city, state, zip)
    2. If no street address, look for coordinates (lat/lon)
    3. If no coordinates, extract the most specific location mentioned
    4. Determine precision level: address > street > intersection > city > region > country
    5. Extract exact source URL and text snippet containing the address (use "N/A" if too vague to search)
    6. Assign confidence based on:
       - Source reliability: .gov/.edu (0.9-1.0), Wikipedia (0.7-0.8), news (0.6-0.8), forums (0.3-0.5)
       - Specificity: exact address (1.0), intersection (0.7), city only (0.3), region (0.1-0.2), country (0.1)
       - Corroboration: multiple sources increase confidence (+0.1 if 2+ sources agree)
    7. Flag if location is a private residence (is_residence = true)
    8. Cross-check coordinates if original coords were provided (should be nearby, within ~1km)
    9. List corroborating evidence and any concerns

    EXAMPLES:
    ✓ "702 Bandley Drive, Fountain, Colorado 80817" → precision: address, confidence: 0.95
    ✓ "Corner of Bandley Dr and Main St" → precision: intersection, confidence: 0.7
    ✓ "Somewhere in Fountain, Colorado" → precision: city, confidence: 0.3
    ✓ "United States" (vague context) → precision: country, confidence: 0.1, concerns: ["Location too vague - insufficient context"]
    ✗ Don't force "United States" → "1600 Pennsylvania Ave" without specific context mentioning White House

    Return a JSON object with the AddressResolution structure:
    {
      "address": "full street address or country/region name if too vague",
      "lat": 37.123 or null,
      "lon": -122.456 or null,
      "precision": "address|street|intersection|city|region|country",
      "source_url": "http://... or 'N/A' if too vague to search",
      "source_snippet": "exact text from source or 'N/A' if too vague",
      "confidence": 0.1 to 1.0,
      "is_residence": false,
      "corroboration": ["evidence 1", "evidence 2"] or [] if too vague,
      "concerns": ["Location too vague - insufficient context"] or other concerns,
      "reasoning": "explanation of how address was found and confidence score, or why location is too vague"
    }
  "#
}


function ClassifyLocation(
  place_name: string,
  place_type: string?,
  note: string?,
  story_title: string,
  story_summary: string
) -> LocationClassification {
  client GPT5Mini
  prompt #"
    You are a location classifier for a geocoding system. Categorize this location into one of three tiers to optimize processing.

    LOCATION:
    Place Name: {{ place_name }}
    Place Type: {{ place_type or "unknown" }}
    Context Note: {{ note or "none" }}

    STORY CONTEXT:
    Title: {{ story_title }}
    Summary: {{ story_summary }}

    CATEGORIZATION RULES:

    1. SKIP - Vague country/region with NO specific clues:
       - Generic country references: "China", "Japan", "Taiwan" WITHOUT company name or city
       - Notes like "supplier region", "generic reference", "country not specified"
       - Large regions: "Asia", "Europe", "Middle East" WITHOUT company/factory context
       → Return category: "skip", reason: why it's too vague

    2. SIMPLE - Well-known landmarks, capitals, or company headquarters:
       - Famous places: "Beijing" (capital), "Tokyo" (capital), "White House"
       - Company HQs with context: "Cupertino, California" + Apple → "1 Infinite Loop, Cupertino, CA 95014"
       - Major landmarks: "Eiffel Tower", "Golden Gate Bridge"
       → Return category: "simple", simple_address: the well-known address, estimated_precision: address/city

    3. RESEARCH - Specific or inferable locations needing web search:
       - Explicit location: "Fountain, Colorado factory", "Fremont plant", "Changsha facility"
       - Company-inferred location: "Quanta factory" (Quanta is Taiwanese → search Taiwan factories)
       - Context clues: Story mentions country/region/year that narrows down location
       - Historical sites requiring research
       - IMPORTANT: If place_name contains a company name (Foxconn, Quanta, Pegatron, etc.):
         * Check story context for country/region mentions
         * Use company's known primary locations (e.g., Quanta = Taiwan, Foxconn = China/Taiwan)
         * If ANY context clue exists (year, country in story, company origin) → RESEARCH
       → Return category: "research", reason: what needs to be researched and what clues exist

    EXAMPLES:

    ✓ "China" + type: country + note: "Supplier region for multi-touch" + story: generic supply chain
      → skip (vague country, no specific facility, no company name)

    ✓ "Cupertino, California" + story about Apple + note: "Apple's home base"
      → simple (1 Infinite Loop, Cupertino, CA 95014)

    ✓ "Beijing" + type: city + note: "Policy document location"
      → simple (Beijing, China - capital city)

    ✓ "Fountain, Colorado" + type: factory + note: "Apple Macintosh factory, 340,000 sq ft"
      → research (specific factory needs address lookup)

    ✓ "Japan" + type: country + note: "Canon manufactured LaserWriter"
      → skip (country-level, no specific Canon factory mentioned, no year/city context)

    ✓ "Quanta factory" + type: factory + note: "(location not specified)" + story: mentions Taiwan supplier, 2010
      → research (Quanta is Taiwanese company, story has Taiwan context + year → search "Quanta factory Taiwan 2010")

    ✓ "Foxconn facility" + type: factory + note: "iPhone production" + story: supply chain in China
      → research (Foxconn has China/Taiwan factories, story context mentions China → search specific facility)

    ✓ "Tokyo, Japan" + note: "dinner with Sony executives at exclusive restaurant"
      → simple (Tokyo, Japan - major city with known coordinates)

    Return JSON with: category, reason, and optionally simple_address + estimated_precision.
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

// GPT5Mini client for fast classification (cheap, no web search)
client<llm> GPT5Mini {
  provider openai-responses
  options {
    model "gpt-5-mini"
  }
}


// ============================================================================
// CLUSTER SUMMARIZATION
// ============================================================================
// Used by abxgeo cluster command to generate narrative summaries for clusters

class ClusterSummary {
  summary string @description("2-3 sentence narrative summary highlighting the story arc at this location")
  key_themes string[] @description("3-5 key themes across stories (e.g., 'manufacturing crises', 'retail expansion')")
  date_range string @description("Date range like '1984-1997' or 'mid-1990s' or '2010s'")
  story_count int @description("Number of stories in this cluster")
}

function SummarizeCluster(
  stories: string[],
  location_name: string,
  zoom_level: int
) -> ClusterSummary {
  client GPT5Mini
  prompt #"
    You are creating a compelling narrative summary for a geographic cluster of stories.

    LOCATION: {{ location_name }}
    ZOOM LEVEL: {{ zoom_level }}
    STORY COUNT: {{ stories | length }}

    STORIES:
    {% for story in stories %}
    {{ loop.index }}. {{ story }}
    {% endfor %}

    TASK:
    Analyze these {{ stories | length }} stories and create a narrative summary that:
    1. Highlights the story arc and key events at this location
    2. Emphasizes what makes this location significant
    3. Captures the time period and evolution of events
    4. Is engaging and informative (2-3 sentences)

    EXAMPLES OF GOOD SUMMARIES:

    Location: Cupertino, California
    Stories: 15 stories about iMac manufacturing, 1998-1999
    ✓ GOOD: "In 1998-1999, Apple's Cupertino campus became the epicenter of the iMac crisis. Engineers battled 'unmanufacturable' designs, faced explosive tooling reviews from Steve Jobs, and orchestrated a dramatic turnaround that shipped the translucent computer on time. The saga included contractor failures, 24/7 'Man on Mir' embeds at suppliers, and Jony Ive's private apologies."

    Location: Shenzhen, China
    Stories: 8 stories about Foxconn iPhone production, 2010-2015
    ✓ GOOD: "Foxconn's Shenzhen facilities transformed from Mac enclosure supplier in the late 1990s to the heart of iPhone mass production in the 2010s. The campus housed hundreds of thousands of workers, faced labor scrutiny from Apple audits, and pioneered high-precision manufacturing techniques that defined modern consumer electronics."

    EXTRACT KEY THEMES:
    Identify 3-5 recurring themes across the stories. Examples:
    - "manufacturing crises"
    - "retail expansion"
    - "supply chain optimization"
    - "labor conditions"
    - "design conflicts"
    - "regulatory challenges"
    - "executive leadership"

    DETERMINE DATE RANGE:
    Extract the date range from the stories. Format examples:
    - "1984-1997" (specific years)
    - "mid-1990s" (decade reference)
    - "2010s" (decade)
    - "1976" (single year if all stories from same year)

    Return JSON with ClusterSummary structure:
    {
      "summary": "2-3 sentence narrative...",
      "key_themes": ["theme1", "theme2", "theme3"],
      "date_range": "YYYY-YYYY or description",
      "story_count": {{ stories | length }}
    }
  "#
}
