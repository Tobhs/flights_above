"""Data update coordinator for Flights Above."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ADSB_POINT_BASES,
    ADSBDB_CALLSIGN_URL,
    CONF_COUNT,
    CONF_RADIUS,
    CONF_REQUIRE_ROUTE,
    CONF_SCAN_INTERVAL,
    DEFAULT_COUNT,
    DEFAULT_RADIUS,
    DEFAULT_REQUIRE_ROUTE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HISTORY_TTL,
    KM_PER_NM,
    MAX_RADAR_BLIPS,
    MAX_RADIUS_NM,
    REQUEST_TIMEOUT,
    ROUTE_CACHE_TTL,
    ROUTE_MISS_TTL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

# Estimated whole-aircraft CO2 output in kg per km flown, by aircraft class.
# These are rough averages for a *very* approximate footprint estimate.
CO2_KG_PER_KM = {
    "widebody": 22.0,
    "narrowbody": 9.5,
    "regional": 5.5,
    "turboprop": 3.2,
    "bizjet": 4.5,
    "piston": 0.9,
    "unknown": 9.0,
}

_WIDEBODY = {
    "A332", "A333", "A337", "A338", "A339", "A342", "A343", "A345", "A346",
    "A359", "A35K", "A388", "B742", "B743", "B744", "B748", "B74S", "B762",
    "B763", "B764", "B772", "B773", "B77L", "B77W", "B77F", "B788", "B789",
    "B78X", "IL96", "MD11",
}
_NARROWBODY = {
    "A318", "A319", "A320", "A321", "A19N", "A20N", "A21N", "B712", "B717",
    "B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739",
    "B37M", "B38M", "B39M", "B3XM", "B752", "B753", "MD82", "MD83", "MD87",
    "MD88", "MD90", "BCS1", "BCS3", "A221", "A223",
}
_REGIONAL = {
    "E170", "E75L", "E75S", "E190", "E195", "E290", "E295", "CRJ1", "CRJ2",
    "CRJ7", "CRJ9", "CRJX", "RJ85", "RJ1H", "F70", "F100", "SU95",
}
_TURBOPROP = {
    "AT43", "AT44", "AT45", "AT46", "AT72", "AT73", "AT75", "AT76", "DH8A",
    "DH8B", "DH8C", "DH8D", "SF34", "SW4", "JS41", "BE20", "C208", "B350", "D328",
}


# Average share of seats filled, used to estimate people on board.
DEFAULT_LOAD_FACTOR = 0.82

# Typical seat count for common ICAO type designators. 0 marks a freighter
# (people on board is then just crew).
_TYPICAL_SEATS = {
    "A332": 260, "A333": 290, "A337": 300, "A338": 290, "A339": 290,
    "A342": 260, "A343": 295, "A345": 315, "A346": 380, "A359": 315,
    "A35K": 366, "A388": 525, "B742": 400, "B743": 400, "B744": 400,
    "B748": 410, "B74S": 380, "B762": 200, "B763": 245, "B764": 245,
    "B772": 305, "B773": 350, "B77L": 300, "B77W": 365, "B77F": 0,
    "B788": 240, "B789": 290, "B78X": 330, "IL96": 300, "MD11": 290,
    "A318": 110, "A319": 140, "A320": 165, "A321": 200, "A19N": 140,
    "A20N": 165, "A21N": 200, "B712": 110, "B717": 110, "B731": 120,
    "B732": 125, "B733": 130, "B734": 146, "B735": 126, "B736": 110,
    "B737": 140, "B738": 178, "B739": 189, "B37M": 172, "B38M": 178,
    "B39M": 189, "B3XM": 200, "B752": 200, "B753": 240, "MD82": 150,
    "MD83": 150, "MD87": 130, "MD88": 150, "MD90": 160, "BCS1": 110,
    "BCS3": 145, "A221": 110, "A223": 145, "E170": 76, "E75L": 82,
    "E75S": 82, "E190": 100, "E195": 120, "E290": 100, "E295": 132,
    "CRJ1": 50, "CRJ2": 50, "CRJ7": 70, "CRJ9": 90, "CRJX": 100,
    "RJ85": 95, "RJ1H": 100, "F70": 80, "F100": 100, "SU95": 98,
    "AT43": 48, "AT44": 48, "AT45": 48, "AT46": 48, "AT72": 70,
    "AT73": 70, "AT75": 70, "AT76": 70, "DH8A": 37, "DH8B": 39,
    "DH8C": 50, "DH8D": 78, "SF34": 34, "SW4": 19, "JS41": 29,
    "BE20": 9, "C208": 9, "B350": 9, "D328": 32,
}

# Fallback seat count when the exact type isn't known but the class is.
_CLASS_SEATS = {
    "widebody": 300,
    "narrowbody": 160,
    "regional": 90,
    "turboprop": 60,
    "bizjet": 8,
    "piston": 3,
    "unknown": None,
}


def _people_on_board(
    type_code: str | None,
    emissions_class: str,
    load_factor: float = DEFAULT_LOAD_FACTOR,
) -> tuple[int | None, int | None]:
    """Estimate (typical_seats, people_on_board) for an aircraft."""
    seats = _TYPICAL_SEATS.get(type_code.upper()) if type_code else None
    if seats is None:
        seats = _CLASS_SEATS.get(emissions_class)
    if seats is None:
        return None, None
    if seats == 0:  # freighter -> crew only
        return 0, 2
    return seats, max(1, round(seats * load_factor))


def _emissions_class(type_code: str | None) -> str:
    """Map an ICAO aircraft type designator to a coarse emissions class."""
    if not type_code:
        return "unknown"
    t = type_code.upper()
    if t in _WIDEBODY:
        return "widebody"
    if t in _NARROWBODY:
        return "narrowbody"
    if t in _REGIONAL:
        return "regional"
    if t in _TURBOPROP:
        return "turboprop"
    if t.startswith(
        (
            "C25", "C52", "C56", "C68", "GLF", "G2", "G5", "G6", "LJ", "CL3",
            "CL6", "FA", "F2TH", "E55P", "E50P", "GALX", "H25", "PC12", "PC24",
            "BE40",
        )
    ):
        return "bizjet"
    if t.startswith(
        ("C15", "C17", "C18", "C20", "P28", "PA", "SR2", "DA2", "DA4", "BE3")
    ):
        return "piston"
    return "unknown"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2, in degrees (0 = north)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _build_progress_bar(pct: float | None, width: int = 16) -> str | None:
    """Return an origin ●━━✈──● destination style bar for the given percent."""
    if pct is None:
        return None
    pct = max(0.0, min(100.0, pct))
    inner = max(width - 2, 1)
    pos = round(pct / 100 * (inner - 1))
    left = "━" * pos
    right = "─" * (inner - 1 - pos)
    return f"●{left}✈{right}● {round(pct)}%"


# Defensive limits for untrusted API data.
MAX_AIRCRAFT_PER_UPDATE = 300  # ignore absurdly large responses
MAX_HISTORY = 200  # cap remembered flights to bound memory
MAX_ROUTE_CACHE = 500  # cap resolved-route cache
MAX_TEXT_LEN = 60  # cap any free-text field from the API


def _finite(value) -> float | None:
    """Return value as a finite float, or None (rejects NaN/inf/garbage)."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _valid_lat(value) -> float | None:
    num = _finite(value)
    return num if num is not None and -90.0 <= num <= 90.0 else None


def _valid_lon(value) -> float | None:
    num = _finite(value)
    return num if num is not None and -180.0 <= num <= 180.0 else None


def _clean_text(value, max_len: int = MAX_TEXT_LEN) -> str | None:
    """Coerce to a trimmed, printable, length-capped string, or None.

    Angle brackets are dropped so the stored value can never carry HTML tags,
    protecting any consumer of these attributes, not just our own card.
    """
    if value is None:
        return None
    text = "".join(
        ch for ch in str(value) if ch.isprintable() and ch not in "<>"
    ).strip()
    return text[:max_len] if text else None


def _safe_callsign(value) -> str:
    """Alphanumeric-only, uppercased callsign/hex for safe use in a URL path."""
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()[:10]


class FlightsAboveCoordinator(DataUpdateCoordinator):
    """Fetch aircraft overhead and enrich them with route + progress data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        opts = {**entry.data, **entry.options}
        self.latitude: float = float(opts[CONF_LATITUDE])
        self.longitude: float = float(opts[CONF_LONGITUDE])
        self.radius_km: float = float(opts.get(CONF_RADIUS, DEFAULT_RADIUS))
        self.count: int = int(opts.get(CONF_COUNT, DEFAULT_COUNT))
        self.require_route: bool = bool(
            opts.get(CONF_REQUIRE_ROUTE, DEFAULT_REQUIRE_ROUTE)
        )
        interval = int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

        self._session = async_get_clientsession(hass)
        # callsign -> (route dict | None, timestamp)
        self._route_cache: dict[str, tuple[dict | None, float]] = {}
        # hex -> flight dict (rolling history of recently seen flights)
        self._history: dict[str, dict] = {}
        # True number of airborne aircraft currently inside the radius.
        self.current_count: int = 0
        # Lightweight positions (bearing + distance) for the radar view.
        self.radar: list[dict] = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> list[dict]:
        aircraft = await self._fetch_aircraft()
        now = time.time()

        # Count every airborne aircraft currently inside the radius, regardless
        # of whether its route can be resolved. This is the true "flights
        # overhead" number. Cheap position-only check, no route lookups.
        in_range = 0
        radar: list[dict] = []
        for ac in aircraft:
            lat = _valid_lat(ac.get("lat"))
            lon = _valid_lon(ac.get("lon"))
            if lat is None or lon is None or ac.get("alt_baro") == "ground":
                continue
            dist = haversine_km(self.latitude, self.longitude, lat, lon)
            if dist > self.radius_km:
                continue
            in_range += 1
            if len(radar) < MAX_RADAR_BLIPS:
                heading = _finite(ac.get("track"))
                alt = _finite(ac.get("alt_baro"))
                radar.append(
                    {
                        "callsign": _safe_callsign(ac.get("flight")) or "?",
                        "distance_km": round(dist, 1),
                        "bearing": round(
                            bearing_deg(self.latitude, self.longitude, lat, lon)
                        ),
                        "heading": (
                            round(heading)
                            if heading is not None and 0 <= heading <= 360
                            else None
                        ),
                        "altitude_ft": (
                            int(alt)
                            if alt is not None and -2000 <= alt <= 100000
                            else None
                        ),
                    }
                )
        self.current_count = in_range
        self.radar = radar

        for ac in aircraft:
            flight = await self._build_flight(ac, now)
            if flight is not None:
                self._history[flight["hex"]] = flight

        # Drop flights we haven't seen for a while.
        self._history = {
            key: value
            for key, value in self._history.items()
            if now - value["last_seen"] <= HISTORY_TTL
        }

        flights = sorted(
            self._history.values(), key=lambda f: f["last_seen"], reverse=True
        )
        # Bound memory: never keep more than MAX_HISTORY flights around.
        if len(flights) > MAX_HISTORY:
            flights = flights[:MAX_HISTORY]
            self._history = {f["hex"]: f for f in flights}
        return flights[: self.count]

    async def _fetch_aircraft(self) -> list[dict]:
        """Query the ADS-B point endpoints until one succeeds."""
        radius_nm = min(int(math.ceil(self.radius_km / KM_PER_NM)), MAX_RADIUS_NM)
        radius_nm = max(radius_nm, 1)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        last_error: Exception | None = None

        for base in ADSB_POINT_BASES:
            url = f"{base}/{self.latitude}/{self.longitude}/{radius_nm}"
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    resp = await self._session.get(url, headers=headers)
                    if resp.status != 200:
                        last_error = UpdateFailed(f"{url} returned HTTP {resp.status}")
                        continue
                    payload = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                continue

            if not isinstance(payload, dict):
                last_error = UpdateFailed(f"{url} returned a non-object body")
                continue
            aircraft = payload.get("ac") or payload.get("aircraft") or []
            if not isinstance(aircraft, list):
                last_error = UpdateFailed(f"{url} returned an unexpected shape")
                continue
            # Only keep dict records, and cap how many we will process.
            return [ac for ac in aircraft if isinstance(ac, dict)][
                :MAX_AIRCRAFT_PER_UPDATE
            ]

        raise UpdateFailed(f"No ADS-B source responded: {last_error}")

    async def _build_flight(self, ac: dict, now: float) -> dict | None:
        """Turn one raw aircraft record into an enriched flight dict."""
        lat = _valid_lat(ac.get("lat"))
        lon = _valid_lon(ac.get("lon"))
        if lat is None or lon is None:
            return None

        alt = ac.get("alt_baro")
        if alt == "ground":  # sitting on the tarmac, not overhead
            return None

        distance_km = haversine_km(self.latitude, self.longitude, lat, lon)
        if distance_km > self.radius_km:
            return None

        # Callsign/hex are used to build the adsbdb request URL, so force them
        # to alphanumeric to prevent any path/query injection.
        route_callsign = _safe_callsign(ac.get("flight"))
        display_callsign = route_callsign or "Unknown"
        hex_id = _safe_callsign(ac.get("hex")) or route_callsign or (
            f"pos_{round(lat, 4)}_{round(lon, 4)}"
        )

        gs = _finite(ac.get("gs"))
        speed_kmh = gs * KM_PER_NM if gs is not None and 0 <= gs <= 1500 else None

        altitude_num = _finite(alt)
        altitude_ft = (
            int(altitude_num)
            if altitude_num is not None and -2000 <= altitude_num <= 100000
            else None
        )

        heading_num = _finite(ac.get("track"))
        heading = (
            round(heading_num, 1)
            if heading_num is not None and 0 <= heading_num <= 360
            else None
        )

        registration = _clean_text(ac.get("r"), 12)
        squawk = _clean_text(ac.get("squawk"), 6)
        aircraft_type = _clean_text(ac.get("t"), 8)
        emissions_class = _emissions_class(aircraft_type)
        seats_typical, people_on_board = _people_on_board(
            aircraft_type, emissions_class
        )

        # Vertical movement / climb state from barometric rate (ft/min).
        vr = _finite(ac.get("baro_rate"))
        vertical_rate_fpm = (
            int(vr) if vr is not None and -20000 <= vr <= 20000 else None
        )
        climb_status = None
        if vertical_rate_fpm is not None:
            if vertical_rate_fpm > 200:
                climb_status = "climbing"
            elif vertical_rate_fpm < -200:
                climb_status = "descending"
            else:
                climb_status = "level"

        flight: dict = {
            "hex": hex_id,
            "callsign": display_callsign,
            "registration": registration,
            "aircraft_type": aircraft_type,
            "latitude": lat,
            "longitude": lon,
            "altitude_ft": altitude_ft,
            "ground_speed_kmh": round(speed_kmh, 1) if speed_kmh else None,
            "heading": heading,
            "vertical_rate_fpm": vertical_rate_fpm,
            "climb_status": climb_status,
            "squawk": squawk,
            "emissions_class": emissions_class,
            "seats_typical": seats_typical,
            "people_on_board": people_on_board,
            "distance_km": round(distance_km, 1),
            "last_seen": now,
            # Route / progress placeholders, filled in below when available.
            "origin_name": None,
            "origin_iata": None,
            "origin_icao": None,
            "origin_country": None,
            "destination_name": None,
            "destination_iata": None,
            "destination_icao": None,
            "destination_country": None,
            "hours_flown": None,
            "hours_remaining": None,
            "hours_total": None,
            "eta": None,
            "progress_percent": None,
            "progress_bar": None,
            "co2_total_kg": None,
            "co2_so_far_kg": None,
            "co2_remaining_kg": None,
            "route_line": None,
        }

        route = await self._get_route(route_callsign)
        if not route and self.require_route:
            # We couldn't identify where this flight is going; skip it.
            return None

        if route:
            flight.update(
                {
                    "origin_name": route["origin_name"],
                    "origin_iata": route["origin_iata"],
                    "origin_icao": route["origin_icao"],
                    "origin_country": route["origin_country"],
                    "destination_name": route["destination_name"],
                    "destination_iata": route["destination_iata"],
                    "destination_icao": route["destination_icao"],
                    "destination_country": route["destination_country"],
                }
            )
            self._add_progress(flight, route, lat, lon, speed_kmh)

        flight["route_line"] = self._build_route_line(flight)
        return flight

    def _add_progress(
        self,
        flight: dict,
        route: dict,
        lat: float,
        lon: float,
        speed_kmh: float | None,
    ) -> None:
        """Compute how far along the route the aircraft is."""
        o_lat, o_lon = route["origin_lat"], route["origin_lon"]
        d_lat, d_lon = route["destination_lat"], route["destination_lon"]
        if None in (o_lat, o_lon, d_lat, d_lon):
            return

        flown = haversine_km(o_lat, o_lon, lat, lon)
        remaining = haversine_km(lat, lon, d_lat, d_lon)
        denom = flown + remaining
        if denom <= 0:
            return

        flight["progress_percent"] = round(flown / denom * 100, 1)
        flight["progress_bar"] = _build_progress_bar(flight["progress_percent"])

        # Very rough CO2 footprint estimate from distance and aircraft class.
        factor = CO2_KG_PER_KM.get(flight["emissions_class"], CO2_KG_PER_KM["unknown"])
        flight["co2_total_kg"] = round(denom * factor)
        flight["co2_so_far_kg"] = round(flown * factor)
        flight["co2_remaining_kg"] = round(remaining * factor)

        if speed_kmh and speed_kmh > 50:
            hours_flown = flown / speed_kmh
            hours_remaining = remaining / speed_kmh
            flight["hours_flown"] = round(hours_flown, 1)
            flight["hours_remaining"] = round(hours_remaining, 1)
            flight["hours_total"] = round(hours_flown + hours_remaining, 1)
            eta = datetime.now(timezone.utc) + timedelta(hours=hours_remaining)
            flight["eta"] = eta.replace(microsecond=0).isoformat()

    @staticmethod
    def _build_route_line(flight: dict) -> str:
        """Human-readable one-liner: LHR ●━━✈──● JFK · 32% · 2.1h / 4.4h."""
        origin = flight["origin_iata"] or flight["origin_icao"] or "???"
        dest = flight["destination_iata"] or flight["destination_icao"] or "???"
        bar = flight["progress_bar"] or "●──────✈──────●"
        parts = [f"{origin} {bar} {dest}"]
        if flight["hours_flown"] is not None:
            parts.append(
                f"{flight['hours_flown']}h done · "
                f"{flight['hours_remaining']}h left · "
                f"{flight['hours_total']}h total"
            )
        elif flight["progress_percent"] is not None:
            parts.append(f"{flight['progress_percent']}% of the way")
        return "  ·  ".join(parts)

    async def _get_route(self, callsign: str) -> dict | None:
        """Resolve a callsign to its origin/destination airports (cached)."""
        if not callsign or callsign == "Unknown":
            return None

        now = time.time()
        cached = self._route_cache.get(callsign)
        if cached is not None:
            value, ts = cached
            ttl = ROUTE_CACHE_TTL if value else ROUTE_MISS_TTL
            if now - ts < ttl:
                return value

        route = await self._fetch_route(callsign)
        # Bound the cache: drop the oldest entries if it grows too large.
        if len(self._route_cache) >= MAX_ROUTE_CACHE:
            oldest = sorted(self._route_cache.items(), key=lambda kv: kv[1][1])
            for key, _ in oldest[: len(oldest) // 2]:
                self._route_cache.pop(key, None)
        self._route_cache[callsign] = (route, now)
        return route

    async def _fetch_route(self, callsign: str) -> dict | None:
        safe = _safe_callsign(callsign)
        if not safe:
            return None
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        url = f"{ADSBDB_CALLSIGN_URL}{safe}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.get(url, headers=headers)
                if resp.status != 200:
                    return None
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

        if not isinstance(payload, dict):
            return None
        response = payload.get("response")
        if not isinstance(response, dict):
            return None  # e.g. {"response": "unknown callsign"}
        flightroute = response.get("flightroute")
        if not isinstance(flightroute, dict):
            return None

        origin = flightroute.get("origin")
        destination = flightroute.get("destination")
        origin = origin if isinstance(origin, dict) else {}
        destination = destination if isinstance(destination, dict) else {}
        return {
            "origin_name": _clean_text(origin.get("name")),
            "origin_iata": _clean_text(origin.get("iata_code"), 4),
            "origin_icao": _clean_text(origin.get("icao_code"), 4),
            "origin_country": _clean_text(origin.get("country_name"), 40),
            "origin_lat": _valid_lat(origin.get("latitude")),
            "origin_lon": _valid_lon(origin.get("longitude")),
            "destination_name": _clean_text(destination.get("name")),
            "destination_iata": _clean_text(destination.get("iata_code"), 4),
            "destination_icao": _clean_text(destination.get("icao_code"), 4),
            "destination_country": _clean_text(destination.get("country_name"), 40),
            "destination_lat": _valid_lat(destination.get("latitude")),
            "destination_lon": _valid_lon(destination.get("longitude")),
        }
