// Team configuration. Each team supports ONE review platform, so it is fixed
// here and shown to the user (read-only) instead of being a dropdown.
// Change these values to match your team's platform.
export const TEAM_PLATFORM = {
  id: "google_reviews",
  label: "Google Reviews",
  // Hostnames a source URL should belong to (used for a light sanity check).
  hostSuffixes: ["google.com", "goo.gl", "g.page"],
} as const;

export const MAX_NAME_LENGTH = 120;
