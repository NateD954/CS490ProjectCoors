// Team configuration. The team supports ONE review platform, so it is fixed here
// and shown to the user (read-only) instead of being a dropdown.
export const TEAM_PLATFORM = {
  id: "GOOGLE_MAPS", // the value the backend and database store
  label: "Google Maps", // what users see
  hostSuffixes: ["google.com"], // hostnames a source URL should belong to
} as const;

// Backend platform values -> display labels
export const PLATFORM_LABELS: Record<string, string> = {
  GOOGLE_MAPS: "Google Maps",
};

// The scraper (services/google_reviews.py) finds a place using the "0x...:0x..."
// id inside the Google Maps URL, so links without it can't be ingested.
export const GOOGLE_PLACE_DATA_ID = /0x[0-9a-fA-F]+:0x[0-9a-fA-F]+/;

export const MAX_NAME_LENGTH = 120;
