# ![](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/mark.png) Flights Above

A Home Assistant custom integration (HACS-ready) that shows the aircraft passing
over a location you choose. For each flight it gives you the callsign, the
departure and arrival airports, and a **progress line** showing how far along the
journey the plane is: hours already flown, hours remaining, and total.

The bundled Lovelace card draws each flight as an origin → ✈ → destination track
with hours, an estimated CO₂ footprint, and people on board (light and dark):

![Flights Above card, light theme](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/preview-light.png) ![Flights Above card, dark theme](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/preview-dark.png)

Turn on `show_radar` and it also draws a radar of **every** aircraft around you,
plotted by real bearing and distance:

![Radar view, light](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/radar-view-light.png) ![Radar view, dark](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/radar-view-dark.png)

All data comes from **free, open community APIs: no account, no API key, nothing
to pay**:

| Purpose | Source | Cost |
|---|---|---|
| Live aircraft positions | [adsb.lol](https://adsb.lol) → falls back to [airplanes.live](https://airplanes.live) | Free, no key |
| Departure / arrival airports | [adsbdb.com](https://www.adsbdb.com) | Free, no key |

Flight-hours are **estimated** from great-circle distances and the aircraft's
ground speed (these APIs don't publish scheduled times), so treat them as a good
approximation rather than an airline timetable.

---

## Installation (HACS)

1. In Home Assistant go to **HACS → ⋮ (top right) → Custom repositories**.
2. Add the URL of this repository, category **Integration**, and click **Add**.
3. Find **Flights Above** in HACS, click **Download**, and **restart Home Assistant**.
4. Go to **Settings → Devices & Services → Add Integration → Flights Above**.

### Manual installation
Copy the `custom_components/flights_above` folder into your Home Assistant
`config/custom_components/` directory and restart.

---

## Configuration

When you add the integration you'll be asked for:

| Field | Meaning |
|---|---|
| **Name** | Friendly name (also used for the entity ids). |
| **Latitude / Longitude** | The address/point to watch. Pre-filled with your Home Assistant location. |
| **Radius (km)** | How far around that point to look (max 400 km; the ADS-B source caps the query at 250 nautical miles ≈ 460 km). |
| **Number of flights (1-3)** | How many of the most recent flights to expose as sensors. |
| **Update interval (s)** | How often to poll (default 60 s). Please keep it reasonable; these are free community APIs. |
| **Only show flights with a known route** | On by default: skips aircraft whose departure/arrival airport can't be identified, so you only see flights with full details. Turn it off to include every aircraft overhead (airports/hours/CO₂ left blank when unknown). |

You can change the radius, count and interval any time via the integration's
**Configure** button.

> Tip: to find the coordinates of any address, right-click it in Google Maps and
> click the lat/long numbers to copy them.

---

## Entities

For an integration named "Flights Above" you get:

- `sensor.flights_above_flights_overhead`: the true number of aircraft currently
  within your radius (not limited by how many flights are displayed). Its
  attributes include a `flights` list summarising the tracked ones.
- `sensor.flights_above_flight_1`, `_flight_2`, `_flight_3`: one per configured
  slot, ordered by most recently seen. State = callsign.

Each flight slot sensor exposes these attributes:

| Attribute | Description |
|---|---|
| `origin_name` / `origin_iata` / `origin_icao` / `origin_country` | Departure airport + country |
| `destination_name` / `destination_iata` / `destination_icao` / `destination_country` | Arrival airport + country |
| `hours_flown` / `hours_remaining` / `hours_total` | Estimated flight time |
| `eta` | Estimated arrival time (ISO timestamp) |
| `progress_percent` | How far along the route (0-100) |
| `progress_bar` | `●━━✈──●` style bar for that percent |
| `route_line` | Full one-line summary (origin, bar, destination, hours) |
| `co2_total_kg` / `co2_so_far_kg` / `co2_remaining_kg` | Estimated CO₂ footprint for the whole aircraft |
| `emissions_class` | Aircraft class used for the CO₂ estimate (widebody, narrowbody, regional, turboprop, bizjet, piston) |
| `people_on_board` / `seats_typical` | Estimated people on board (typical seats × load factor) and the typical seat count for the type |
| `latitude` / `longitude` / `altitude_ft` | Current position |
| `ground_speed_kmh` / `heading` / `distance_km` | Movement + distance from your point |
| `vertical_rate_fpm` / `climb_status` | Climb rate and `climbing` / `descending` / `level` |
| `squawk` | Transponder code |
| `registration` / `aircraft_type` | Tail number and ICAO type code |
| `in_range` | Whether this slot currently holds a flight |

The integration keeps a **30-minute rolling history**, so the slots keep showing
the *last* flights that passed through even when the sky is momentarily empty.

> **CO₂ and people-on-board figures are rough estimates.** CO₂ comes from the flight
> distance times an average fuel-burn factor for the aircraft class; people on board
> comes from the type's typical seat count times an average load factor (~82%, crew
> only for freighters). Good for a sense of scale and comparison, not exact figures.

---

## Custom Lovelace card (graphical)

The integration ships a **graphical card** that draws each flight as an
origin → ✈ → destination track with the plane animated to its real progress
position, plus hour labels and info chips.

```
 LHR ●━━━━━━✈──────────● JFK
 2.5h flown        38%        4.1h left
              6.6h total flight time
```

### Enabling the card

The integration **serves the card file automatically** at
`/flights_above/flights-above-card.js` and tries to register it as a dashboard
resource for you. If your dashboard is in **storage mode** (the default), it
should just work after a restart.

If the card shows as *"Custom element doesn't exist"*, add the resource manually:

1. Go to **Settings → Dashboards → ⋮ → Resources → Add resource**.
2. URL: `/flights_above/flights-above-card.js`
3. Type: **JavaScript Module**, then reload the browser (Ctrl/Cmd-Shift-R).

> YAML-mode dashboards: add it under `lovelace: resources:` in `configuration.yaml`:
> ```yaml
> lovelace:
>   resources:
>     - url: /flights_above/flights-above-card.js
>       type: module
> ```

### Using the card

```yaml
type: custom:flights-above-card
title: Flights Above
entity_prefix: sensor.flights_above
```

**Card options:**

| Option | Default | Description |
|---|---|---|
| `title` | `Flights Above` | Card header. Set to `""` to hide it. |
| `entity_prefix` | `sensor.flights_above` | Prefix used to find the `_flight_1…N` and `_flights_overhead` sensors. Change it if you named the integration differently. |
| `flights` | *(auto)* | Optional explicit list of flight sensor entity ids instead of using the prefix. |
| `count_entity` | *(auto)* | Optional explicit "flights overhead" count sensor. |
| `max` | `3` | How many flights to display at once. |
| `sort` | `recent` | Order flights by `recent` (most recently seen) or `distance` (nearest first). |
| `show_details` | `true` | Show aircraft type / registration and the info chips. |
| `show_empty` | `true` | Show a "No flights in range" message when the sky is empty. |
| `show_radar` | `false` | Show a radar of **every** aircraft in range around your location. |
| `select_seconds` | `30` | How long a plane tapped on the radar stays pinned before the list returns. |

### Radar view

Set `show_radar: true` to draw a radar around your location. Your position is the
centre, north is up, and every aircraft currently inside your radius is plotted by
its real bearing and distance (not just the ones listed below it):

![Radar view, light](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/radar-view-light.png) ![Radar view, dark](https://raw.githubusercontent.com/Tobhs/flights_above/main/assets/radar-view-dark.png)

```yaml
type: custom:flights-above-card
title: Flights Above
entity_prefix: sensor.flights_above
max: 1
show_details: true
show_radar: true
```

The rings mark a third, two thirds, and the full radius you configured. Callsigns
are labelled when six or fewer aircraft are in range, so it stays readable when the
sky is busy, and each blip has a short line showing **which way that aircraft is
heading**.

**Tap a plane** on the radar and the section underneath switches to that aircraft's
details instead of the usual list. It goes back to the normal list on its own after
30 seconds (change it with `select_seconds`), or tap the same plane again to switch
back straight away. If you tap an aircraft that is not one of your tracked flight
slots, you still get its distance, altitude, bearing and heading.

Show a single flight (e.g. the nearest one):

```yaml
type: custom:flights-above-card
title: Flights Above
entity_prefix: sensor.flights_above
max: 1
show_details: true
show_empty: true
```

Add `sort: distance` to make that single card always show the **closest** aircraft
(by default the list is ordered by most recently seen):

```yaml
type: custom:flights-above-card
title: Nearest flight
entity_prefix: sensor.flights_above
max: 1
sort: distance
```

Example with explicit entities:

```yaml
type: custom:flights-above-card
title: Overhead now
flights:
  - sensor.flights_above_flight_1
  - sensor.flights_above_flight_2
count_entity: sensor.flights_above_flights_overhead
```

### Prefer a Markdown card instead?

Every value is also available as a plain attribute, so a simple Markdown card
works too:

```yaml
type: markdown
title: ✈ Flights Above
content: |
  {% set count = states('sensor.flights_above_flights_overhead') | int(0) %}
  **{{ count }} flight(s) in range**

  {% for i in range(1, 4) %}
  {%- set e = 'sensor.flights_above_flight_' ~ i %}
  {%- if states(e) not in ['unknown', 'unavailable', 'None'] and states(e) is not none %}

  ### {{ states(e) }}
  {{ state_attr(e, 'origin_name') or '?' }} → {{ state_attr(e, 'destination_name') or '?' }}

  `{{ state_attr(e, 'route_line') }}`
  {%- endif %}
  {%- endfor %}
```

---

## Notes & limitations

- **Coverage** depends on volunteer ADS-B receivers near you. Well-covered areas
  (Europe, North America, cities) work best; remote areas may see fewer aircraft.
- **Route lookups** rely on adsbdb's crowd-sourced database; some callsigns
  (private/GA flights, brand-new routes) won't resolve, in which case airports and
  hours are left blank but the position is still shown.
- **Flight hours are estimates.** They assume constant ground speed along the
  great-circle route and will drift near takeoff/landing when the plane is slow.
- Please be a good citizen and don't hammer the free APIs with very short update
  intervals.

## Credits

- Aircraft data © the [adsb.lol](https://adsb.lol) and
  [airplanes.live](https://airplanes.live) communities.
- Route data © [adsbdb.com](https://www.adsbdb.com).

Licensed under the MIT License.
