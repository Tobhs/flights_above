"""Constants for the Flights Above integration."""

from __future__ import annotations

DOMAIN = "flights_above"
DEFAULT_NAME = "Flights Above"

# Configuration keys
CONF_RADIUS = "radius"
CONF_COUNT = "count"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_REQUIRE_ROUTE = "require_route"

# Defaults / limits
DEFAULT_RADIUS = 30.0  # km
DEFAULT_COUNT = 3
DEFAULT_SCAN_INTERVAL = 60  # seconds
DEFAULT_REQUIRE_ROUTE = True
MIN_COUNT = 1
MAX_COUNT = 3
MAX_RADIUS_KM = 400.0
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

# How long a flight stays in the "recently passed through" history (seconds).
HISTORY_TTL = 1800  # 30 minutes
# How long a resolved callsign -> route lookup is cached (seconds).
ROUTE_CACHE_TTL = 21600  # 6 hours
# How long a "not found" route lookup is cached before retrying (seconds).
ROUTE_MISS_TTL = 3600  # 1 hour

# Data sources (all free, no API key required).
# Position sources are tried in order until one responds successfully.
# Both use the same path shape: <base>/{lat}/{lon}/{radius_in_nautical_miles}
ADSB_POINT_BASES = [
    "https://api.adsb.lol/v2/point",
    "https://api.airplanes.live/v2/point",
]
# Route / airport lookup by callsign.
ADSBDB_CALLSIGN_URL = "https://api.adsbdb.com/v0/callsign/"

ATTRIBUTION = "Live data from adsb.lol / airplanes.live, routes from adsbdb.com"

USER_AGENT = "home-assistant-flights-above/1.0"
REQUEST_TIMEOUT = 25  # seconds

# Nautical miles per kilometre conversion helpers
KM_PER_NM = 1.852
MAX_RADIUS_NM = 250  # adsb.lol / airplanes.live point endpoint hard cap
