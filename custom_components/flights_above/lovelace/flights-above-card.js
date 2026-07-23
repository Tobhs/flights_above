/**
 * Flights Above - custom Lovelace card
 * Draws origin ✈ destination progress tracks for the Flights Above integration.
 * Dependency-free custom element; works when added as a dashboard resource.
 */

const CARD_VERSION = "1.0.2";

const PLANE_SVG = `
<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
  <path fill="currentColor" d="M21 16v-2l-8-5V3.5A1.5 1.5 0 0 0 11.5 2 1.5 1.5 0 0 0 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z"/>
</svg>`;

// Escape any value coming from sensor attributes (which originate from a
// third-party API) before it is placed into innerHTML. Prevents HTML/script
// injection if the upstream data ever contains markup.
const ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ESC_MAP[c]);
}

class FlightsAboveCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: config.title !== undefined ? config.title : "Flights Above",
      entity_prefix: config.entity_prefix || "sensor.flights_above",
      flights: Array.isArray(config.flights) ? config.flights : null,
      count_entity: config.count_entity || null,
      max: config.max || 3,
      show_details: config.show_details !== false,
      show_empty: config.show_empty !== false,
    };
    if (!this._built) {
      this.attachShadow({ mode: "open" });
      this._built = true;
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 1 + (this._config ? this._config.max : 3);
  }

  static getStubConfig() {
    return { entity_prefix: "sensor.flights_above" };
  }

  _flightEntityIds() {
    if (this._config.flights) return this._config.flights;
    const ids = [];
    for (let i = 1; i <= this._config.max; i++) {
      ids.push(`${this._config.entity_prefix}_flight_${i}`);
    }
    return ids;
  }

  _countEntityId() {
    return this._config.count_entity || `${this._config.entity_prefix}_flights_overhead`;
  }

  _fmtHours(h) {
    if (h === null || h === undefined) return null;
    return `${Number(h).toFixed(1)}h`;
  }

  _clampPercent(p) {
    if (p === null || p === undefined || isNaN(p)) return null;
    return Math.max(0, Math.min(100, Number(p)));
  }

  _renderFlight(stateObj) {
    const a = stateObj.attributes;
    const callsign = esc(stateObj.state);
    const origin = esc(a.origin_iata || a.origin_icao || "???");
    const dest = esc(a.destination_iata || a.destination_icao || "???");
    const originName = esc(a.origin_name || "");
    const destName = esc(a.destination_name || "");
    const pct = this._clampPercent(a.progress_percent);
    const planePos = pct === null ? 50 : Math.max(4, Math.min(96, pct));
    const knownRoute = a.progress_percent !== null && a.progress_percent !== undefined;

    const flown = this._fmtHours(a.hours_flown);
    const left = this._fmtHours(a.hours_remaining);
    const total = this._fmtHours(a.hours_total);

    const chips = [];
    if (a.distance_km !== null && a.distance_km !== undefined)
      chips.push(`${a.distance_km} km away`);
    if (a.altitude_ft) chips.push(`${a.altitude_ft.toLocaleString()} ft`);
    if (a.ground_speed_kmh) chips.push(`${Math.round(a.ground_speed_kmh)} km/h`);
    if (a.people_on_board) chips.push(`≈ ${a.people_on_board} on board`);
    if (a.climb_status && a.climb_status !== "level")
      chips.push(a.climb_status === "climbing" ? "↑ climbing" : "↓ descending");
    if (a.co2_total_kg)
      chips.push(`${Number(a.co2_total_kg).toLocaleString()} kg CO₂`);
    if (a.eta) {
      const t = new Date(a.eta);
      if (!isNaN(t)) {
        chips.push(
          `ETA ${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
        );
      }
    }

    const subtitle = this._config.show_details
      ? esc([a.aircraft_type, a.registration].filter(Boolean).join(" · "))
      : "";

    return `
      <div class="flight">
        <div class="row head">
          <div class="callsign">${callsign}</div>
          ${subtitle ? `<div class="subtitle">${subtitle}</div>` : ""}
        </div>

        <div class="row airports">
          <div class="airport left">
            <div class="code">${origin}</div>
            <div class="aname">${originName}</div>
          </div>
          <div class="airport right">
            <div class="code">${dest}</div>
            <div class="aname">${destName}</div>
          </div>
        </div>

        <div class="track ${knownRoute ? "" : "unknown"}">
          <div class="line"></div>
          <div class="fill" style="width:${pct === null ? 0 : pct}%"></div>
          <div class="dot origin"></div>
          <div class="dot dest"></div>
          <div class="plane" style="left:${planePos}%">${PLANE_SVG}</div>
        </div>

        <div class="row hours">
          <div class="h left">${flown ? `${flown} flown` : ""}</div>
          <div class="h mid">${pct === null ? "route unknown" : `${Math.round(pct)}%`}</div>
          <div class="h right">${left ? `${left} left` : ""}</div>
        </div>
        ${total ? `<div class="total">${total} total flight time</div>` : ""}
        ${chips.length ? `<div class="chips">${chips.map((c) => `<span>${esc(c)}</span>`).join("")}</div>` : ""}
      </div>`;
  }

  _render() {
    if (!this._hass || !this._config) return;

    const entities = this._flightEntityIds();
    const flights = entities
      .map((id) => this._hass.states[id])
      .filter(
        (s) =>
          s &&
          s.state &&
          !["unknown", "unavailable", "None"].includes(s.state) &&
          s.attributes.in_range !== false
      );

    const countObj = this._hass.states[this._countEntityId()];
    const count = countObj ? countObj.state : flights.length;

    let body;
    if (flights.length === 0) {
      body = this._config.show_empty
        ? `<div class="empty">No flights currently in range.</div>`
        : "";
    } else {
      body = flights.map((s) => this._renderFlight(s)).join("");
    }

    const header = this._config.title
      ? `<div class="card-header">
           <span>${esc(this._config.title)}</span>
           <span class="count">${esc(count)}</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>
        ${header}
        <div class="content">${body}</div>
      </ha-card>`;
  }

  _styles() {
    return `
      ha-card { overflow: hidden; }
      .card-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 16px 16px 8px; font-size: 1.35rem; font-weight: 500;
        color: var(--ha-card-header-color, var(--primary-text-color));
      }
      .card-header .count {
        font-size: 0.85rem; font-weight: 500; padding: 2px 10px;
        border-radius: 12px; background: var(--primary-color); color: var(--text-primary-color, #fff);
      }
      .content { padding: 0 16px 12px; }
      .flight {
        padding: 12px 0; border-top: 1px solid var(--divider-color);
      }
      .content > .flight:first-child { border-top: none; }
      .row { display: flex; align-items: baseline; justify-content: space-between; }
      .head { margin-bottom: 8px; }
      .callsign {
        font-size: 1.25rem; font-weight: 600; letter-spacing: 0.5px;
        color: var(--primary-text-color);
      }
      .subtitle { font-size: 0.8rem; color: var(--secondary-text-color); }
      .airports { margin-bottom: 6px; }
      .airport .code {
        font-size: 1.05rem; font-weight: 700; color: var(--primary-text-color);
      }
      .airport.right { text-align: right; }
      .airport .aname {
        font-size: 0.72rem; color: var(--secondary-text-color);
        max-width: 45vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .track {
        position: relative; height: 26px; margin: 6px 6px 2px;
      }
      .track .line, .track .fill {
        position: absolute; top: 50%; height: 3px; border-radius: 3px; transform: translateY(-50%);
      }
      .track .line { left: 0; right: 0; background: var(--divider-color); }
      .track .fill {
        left: 0; background: var(--primary-color);
        transition: width 1.2s ease;
      }
      .track.unknown .fill { background: var(--disabled-text-color, #9e9e9e); }
      .dot {
        position: absolute; top: 50%; width: 11px; height: 11px; border-radius: 50%;
        transform: translate(-50%, -50%); background: var(--primary-text-color);
        border: 2px solid var(--card-background-color, var(--ha-card-background, #fff));
      }
      .dot.origin { left: 0; }
      .dot.dest { left: 100%; }
      .plane {
        position: absolute; top: 50%; transform: translate(-50%, -50%);
        color: var(--primary-color); line-height: 0;
        transition: left 1.2s ease;
        filter: drop-shadow(0 1px 1px rgba(0,0,0,0.3));
      }
      .track.unknown .plane { color: var(--disabled-text-color, #9e9e9e); }
      .plane svg { transform: rotate(45deg); display: block; }
      .hours { margin-top: 6px; font-size: 0.8rem; color: var(--secondary-text-color); }
      .hours .mid { color: var(--primary-color); font-weight: 600; }
      .hours .right { text-align: right; }
      .total {
        text-align: center; font-size: 0.72rem; color: var(--secondary-text-color);
        margin-top: 2px;
      }
      .chips {
        margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;
        justify-content: center;
      }
      .chips span {
        font-size: 0.72rem; padding: 2px 8px; border-radius: 10px; white-space: nowrap;
        background: var(--secondary-background-color); color: var(--secondary-text-color);
      }
      .empty {
        padding: 24px 8px; text-align: center; color: var(--secondary-text-color);
      }
    `;
  }
}

customElements.define("flights-above-card", FlightsAboveCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "flights-above-card",
  name: "Flights Above Card",
  description: "Shows overhead flights with an origin → plane → destination progress track.",
  preview: false,
});

// eslint-disable-next-line no-console
console.info(
  `%c FLIGHTS-ABOVE-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;",
  "color:#03a9f4;background:#fff;"
);
