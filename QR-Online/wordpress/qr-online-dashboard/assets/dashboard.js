/* QR-Online Dashboard: der Tracker -- Links mit ihren Scans als Graphen, nur zum Ansehen.
 * Angelegt, geaendert, gestaltet und geloescht wird ausschliesslich in der App QR-Online.
 *
 * Spricht nur /wp-json/qr-online/v1/ an; das Plugin reicht die Aufrufe mit dem
 * API-Schluessel an den QR-Server weiter. Gezaehlt wird nach lokaler Zeit des Browsers
 * (wie qronline/stats.py): ein Scan um 23:30 Uhr gehoert zu diesem Tag, auch wenn es in
 * UTC schon morgen ist.
 */
(function () {
  "use strict";

  const CFG = window.QR_ONLINE || {};
  const RANGES = [["7 Tage", 7], ["30 Tage", 30], ["90 Tage", 90], ["1 Jahr", 365]];
  const WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const LANGUAGES = {de: "Deutsch", en: "Englisch", fr: "Französisch", es: "Spanisch",
    it: "Italienisch", nl: "Niederländisch", pl: "Polnisch", tr: "Türkisch", ru: "Russisch",
    uk: "Ukrainisch", pt: "Portugiesisch", ar: "Arabisch", zh: "Chinesisch", ja: "Japanisch",
    ko: "Koreanisch", cs: "Tschechisch", da: "Dänisch", sv: "Schwedisch", no: "Norwegisch",
    nb: "Norwegisch", fi: "Finnisch", el: "Griechisch", hu: "Ungarisch", ro: "Rumänisch",
    hr: "Kroatisch", sr: "Serbisch", bg: "Bulgarisch", fa: "Persisch"};
  const SVG = "http://www.w3.org/2000/svg";
  const store = {
    get(k, d) { try { return localStorage.getItem("qro-" + k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("qro-" + k, v); } catch (e) { /* egal */ } },
  };

  const state = {links: [], current: null, days: Number(store.get("days", "30")) || 30, filter: ""};
  const root = document.getElementById("qro-app");

  // ------------------------------------------------------------ Hilfen

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c != null && c !== false) node.append(c instanceof Node ? c : String(c));
    }
    return node;
  }

  function svg(tag, attrs) {
    const node = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  async function api(method, path, body, query) {
    // Ohne „schöne“ Permalinks ist CFG.api …/?rest_route=/qr-online/v1/ – dann mit & anhängen
    let url = CFG.api + path;
    if (query) url += (url.includes("?") ? "&" : "?") + new URLSearchParams(query);
    const res = await fetch(url, {
      method, credentials: "same-origin",
      headers: Object.assign({"X-WP-Nonce": CFG.nonce},
        body ? {"Content-Type": "application/json"} : {}),
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* unten */ }
    if (!res.ok) {
      throw new Error((data && (data.message || data.error)) ||
        `Unerwartete Antwort (HTTP ${res.status}).`);
    }
    return data;
  }

  function parseTs(ts) {
    const d = ts ? new Date(ts) : null;
    return d && !isNaN(d) ? d : null;
  }

  function dayKey(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function addDays(d, n) {
    const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    x.setDate(x.getDate() + n);
    return x;
  }

  function shortDate(d) {
    return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.`;
  }

  /** „heute 14:05“, „gestern 09:12“, sonst das Datum – wie app.local_time. */
  function localTime(ts) {
    const t = parseTs(ts);
    if (!t) return "–";
    const hm = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
    const today = new Date();
    if (dayKey(t) === dayKey(today)) return "heute " + hm;
    if (dayKey(t) === dayKey(addDays(today, -1))) return "gestern " + hm;
    return shortDate(t) + t.getFullYear();
  }

  function title(link) { return link.label || link.target; }
  function plural(n) { return `${n} ${n === 1 ? "Scan" : "Scans"}`; }

  // ------------------------------------------------------------ Auswertung

  function parseScans(rows) {
    return rows.map((r) => ({t: parseTs(r.ts), device: r.device || "?", os: r.os || "?",
      lang: r.lang || "?"})).filter((s) => s.t);
  }

  function inRange(scans, days, today) {
    const first = dayKey(addDays(today, -(days - 1))), last = dayKey(today);
    return scans.filter((s) => { const k = dayKey(s.t); return k >= first && k <= last; });
  }

  function daily(scans, days, today) {
    const counts = {};
    for (const s of scans) counts[dayKey(s.t)] = (counts[dayKey(s.t)] || 0) + 1;
    const out = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = addDays(today, -i);
      out.push([d, counts[dayKey(d)] || 0]);
    }
    return out;
  }

  function weekly(perDay) {
    const weeks = new Map();
    for (const [d, n] of perDay) {
      const monday = addDays(d, -((d.getDay() + 6) % 7));
      const k = dayKey(monday);
      if (!weeks.has(k)) weeks.set(k, [monday, 0]);
      weeks.get(k)[1] += n;
    }
    return [...weeks.values()];
  }

  function count(scans, fn, keys) {
    const c = new Map(keys.map((k) => [k, 0]));
    for (const s of scans) c.set(fn(s), (c.get(fn(s)) || 0) + 1);
    return c;
  }

  function breakdown(scans, attr, top = 6) {
    const name = attr === "lang"
      ? (v) => (v === "" || v === "?" ? "unbekannt" : LANGUAGES[v] || v)
      : (v) => v;
    let items = [...count(scans, (s) => name(s[attr]), []).entries()].sort((a, b) => b[1] - a[1]);
    if (items.length > top) {
      const rest = items.slice(top - 1).reduce((sum, [, n]) => sum + n, 0);
      items = items.slice(0, top - 1).concat([["Andere", rest]]);
    }
    return items;
  }

  // ------------------------------------------------------------ Diagramme

  /** Senkrechte Balken (Verlauf); Beschriftung nur jede n-te Spalte, Tooltip per <title>.
   *  Gezeichnet in der echten Breite der Karte, damit die Schrift nicht mitschrumpft. */
  function columnChart(items, opts = {}) {
    const W = Math.max(200, opts.width || 640), H = opts.height || 200, padL = 30, padB = 22, padT = 8;
    const max = Math.max(1, ...items.map(([, n]) => n));
    const step = max <= 5 ? 1 : Math.ceil(max / 4);
    const top = Math.ceil(max / step) * step;
    const s = svg("svg", {viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "qro-chart", role: "img"});
    const plotH = H - padB - padT, plotW = W - padL - 4;
    for (let v = 0; v <= top; v += step) {
      const y = padT + plotH - (v / top) * plotH;
      s.append(svg("line", {x1: padL, x2: W - 4, y1: y, y2: y, class: "qro-grid"}));
      const t = svg("text", {x: padL - 6, y: y + 3, class: "qro-axis", "text-anchor": "end"});
      t.textContent = v;
      s.append(t);
    }
    const bw = plotW / items.length;
    // So viele Beschriftungen, wie nebeneinander passen (gut 6 px je Zeichen plus Abstand)
    const labelW = Math.max(...items.map(([label]) => String(label).length)) * 6.5 + 10;
    const every = Math.max(1, Math.ceil(items.length / Math.max(2, Math.floor(plotW / labelW))));
    items.forEach(([label, n, tip], i) => {
      const h = (n / top) * plotH;
      const g = svg("g", {class: "qro-bar"});
      // Unsichtbare volle Spalte, damit auch Tage mit 0 einen Tooltip haben
      g.append(svg("rect", {x: padL + i * bw, y: padT, width: bw, height: plotH, class: "qro-hit"}));
      g.append(svg("rect", {x: padL + i * bw + bw * 0.15, y: padT + plotH - h,
        width: Math.max(1, bw * 0.7), height: h, rx: Math.min(3, bw * 0.2)}));
      const tt = svg("title", {});
      tt.textContent = `${tip || label}: ${plural(n)}`;
      g.append(tt);
      s.append(g);
      if (i % every === 0) {
        const t = svg("text", {x: padL + i * bw + bw / 2, y: H - 6, class: "qro-axis",
          "text-anchor": "middle"});
        t.textContent = label;
        s.append(t);
      }
    });
    return s;
  }

  /** Anteile in % als waagerechte Balken. */
  function shareChart(items) {
    const total = items.reduce((sum, [, n]) => sum + n, 0);
    if (!total) return el("p", {class: "qro-empty"}, "Keine Scans im Zeitraum");
    return el("ul", {class: "qro-shares"}, items.map(([label, n]) => {
      const pct = Math.round((n / total) * 100);
      return el("li", {title: `${label}: ${plural(n)}`},
        el("span", {class: "qro-share-label"}, label),
        el("span", {class: "qro-share-track"},
          el("span", {class: "qro-share-fill", style: `width:${(n / total) * 100}%`})),
        el("span", {class: "qro-share-value"}, pct + " %"));
    }));
  }

  /** Platzhalter fuer ein Balkendiagramm; drawCharts() zeichnet es, sobald die Breite feststeht. */
  function plot(items, opts) {
    const box = el("div", {class: "qro-plot"});
    box.qroChart = [items, opts || {}];
    return box;
  }

  function drawCharts() {
    const boxes = root.querySelectorAll(".qro-plot");
    // Erst alle leeren: die alten Diagramme wuerden die Breite verfaelschen
    boxes.forEach((box) => box.replaceChildren());
    for (const box of boxes) {
      const [items, opts] = box.qroChart;
      box.replaceChildren(columnChart(items, Object.assign({width: box.clientWidth}, opts)));
    }
  }

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawCharts, 150);
  });

  function card(heading, body, extra) {
    return el("section", {class: "qro-card " + (extra || "")}, el("h3", {}, heading), body);
  }

  // ------------------------------------------------------------ Oberflaeche

  let statusTimer = null;
  function status(text, kind) {
    const bar = root.querySelector(".qro-status");
    if (!bar) return;
    bar.textContent = text || "";
    bar.className = "qro-status" + (kind ? " is-" + kind : "");
    clearTimeout(statusTimer);
    if (kind === "ok") statusTimer = setTimeout(() => status(""), 4000);
  }

  function layout() {
    root.replaceChildren(
      el("div", {class: "qro-toolbar"},
        el("button", {class: "button", type: "button", onclick: refresh}, "Aktualisieren"),
        el("span", {class: "qro-status", role: "status", "aria-live": "polite"}),
        el("a", {class: "qro-settings", href: CFG.settings}, "Einstellungen")),
      el("div", {class: "qro-main"},
        el("aside", {class: "qro-list"},
          el("input", {type: "search", class: "qro-search", placeholder: "Links durchsuchen …",
            "aria-label": "Links durchsuchen", value: state.filter,
            oninput: (e) => { state.filter = e.target.value; renderList(); }}),
          el("div", {class: "qro-items"})),
        el("div", {class: "qro-details"})));
  }

  function renderList() {
    const box = root.querySelector(".qro-items");
    const q = state.filter.trim().toLowerCase();
    const links = state.links.filter((l) => !q ||
      [l.label, l.target, l.code].some((v) => (v || "").toLowerCase().includes(q)));
    if (!state.links.length) {
      box.replaceChildren(el("p", {class: "qro-empty"}, "Noch keine Links. Angelegt werden sie in der App QR-Online."));
      return;
    }
    box.replaceChildren(...links.map((l) => el("button", {
      type: "button", class: "qro-item" + (state.current && state.current.code === l.code ? " is-selected" : ""),
      onclick: () => select(l.code)},
    el("strong", {}, title(l)),
    el("span", {}, `${l.code} · ${plural(l.scans)}`))));
    if (!links.length) box.append(el("p", {class: "qro-empty"}, "Kein Treffer."));
  }

  function renderDetails() {
    const box = root.querySelector(".qro-details");
    const link = state.current;
    if (!link) {
      box.replaceChildren(el("div", {class: "qro-card qro-empty"},
        state.links.length ? "Links auswählen, um die Scans zu sehen." :
          "Noch keine QR-Links. Angelegt und gestaltet werden sie in der App QR-Online; " +
          "hier erscheinen sie mit ihren Scans."));
      return;
    }
    const target = /^https?:\/\//i.test(link.target)
      ? el("a", {href: link.target, target: "_blank", rel: "noopener noreferrer"}, link.target)
      : link.target;
    box.replaceChildren(
      el("div", {class: "qro-card qro-head"},
        el("div", {class: "qro-head-text"},
          el("h2", {}, title(link)),
          el("p", {}, el("span", {class: "qro-muted"}, "QR-Adresse "), el("code", {}, link.url),
            " ", el("button", {type: "button", class: "button button-small", onclick: () => copy(link.url)},
              "Kopieren")),
          el("p", {}, el("span", {class: "qro-muted"}, "Ziel "), target),
          el("p", {class: "qro-muted qro-hint"}, "Ziel ändern, QR-Code gestalten und speichern: " +
            "in der App QR-Online. Der gedruckte Code bleibt dabei gültig."))),
      el("div", {class: "qro-range", role: "group", "aria-label": "Zeitraum"},
        RANGES.map(([label, days]) => el("button", {
          type: "button", class: "button" + (days === state.days ? " is-active" : ""),
          "aria-pressed": String(days === state.days),
          onclick: () => { state.days = days; store.set("days", days); renderDetails(); loadScans(); }},
        label))),
      el("div", {class: "qro-tiles"},
        tile("Im Zeitraum", "…", "range"), tile("Heute", "…", "today"),
        tile("Insgesamt", String(link.scans)), tile("Letzter Scan", localTime(link.last_scan))),
      el("div", {class: "qro-charts"}, el("div", {class: "qro-card qro-wide qro-empty"}, "Lade Scans …")));
  }

  function tile(label, value, key) {
    return el("div", {class: "qro-tile"}, el("span", {}, label),
      el("strong", key ? {"data-tile": key} : {}, value));
  }

  function renderStats(rows) {
    const today = new Date(), days = state.days;
    const scans = inRange(parseScans(rows), days, today);
    const perDay = daily(scans, days, today);
    root.querySelector('[data-tile="range"]').textContent = scans.length;
    root.querySelector('[data-tile="today"]').textContent = perDay[perDay.length - 1][1];
    const time = days > 90
      ? card("Scans pro Woche", plot(weekly(perDay).map(([d, n]) =>
        [shortDate(d), n, "Woche ab " + shortDate(d)]), {height: 220}), "qro-wide")
      : card("Scans pro Tag", plot(perDay.map(([d, n]) =>
        [shortDate(d), n, WEEKDAYS[(d.getDay() + 6) % 7] + " " + shortDate(d)]),
      {height: 220}), "qro-wide");
    const hours = count(scans, (s) => s.t.getHours(), [...Array(24).keys()]);
    const wd = count(scans, (s) => (s.t.getDay() + 6) % 7, [0, 1, 2, 3, 4, 5, 6]);
    root.querySelector(".qro-charts").replaceChildren(
      time,
      card("Uhrzeit", plot([...hours].map(([h, n]) => [String(h), n, `${h}–${h + 1} Uhr`])), "qro-two"),
      card("Wochentag", plot([...wd].map(([i, n]) => [WEEKDAYS[i], n]))),
      card("Gerät", shareChart(breakdown(scans, "device"))),
      card("Betriebssystem", shareChart(breakdown(scans, "os"))),
      card("Sprache", shareChart(breakdown(scans, "lang"))));
    drawCharts();
  }

  // ------------------------------------------------------------ Ablauf

  async function refresh() {
    status("Lade Links …");
    try {
      state.links = await api("GET", "links");
      status("");
    } catch (e) {
      status(e.message, "error");
      return;
    }
    const code = state.current ? state.current.code : store.get("code", "");
    state.current = state.links.find((l) => l.code === code) || state.links[0] || null;
    renderList();
    renderDetails();
    loadScans();
  }

  function select(code) {
    state.current = state.links.find((l) => l.code === code) || null;
    if (state.current) store.set("code", code);
    renderList();
    renderDetails();
    loadScans();
  }

  let scanRequest = 0;
  async function loadScans() {
    const link = state.current;
    if (!link) return;
    const ticket = ++scanRequest;
    // Einen Tag Puffer fuer den Zeitzonen-Versatz (stats.query_since)
    const since = dayKey(addDays(new Date(), -state.days));
    try {
      const rows = await api("GET", "scans/" + link.code, null, {since});
      if (ticket === scanRequest) renderStats(rows);
    } catch (e) {
      if (ticket === scanRequest) status(e.message, "error");
    }
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      status("✓ Link kopiert", "ok");
    } catch (e) {
      window.prompt("Link kopieren:", text);
    }
  }

  if (!root) return;
  if (!CFG.configured) {
    root.replaceChildren(el("div", {class: "notice notice-warning inline"},
      el("p", {}, "Noch kein QR-Server eingetragen. ",
        el("a", {href: CFG.settings}, "Zu den Einstellungen"))));
    return;
  }
  layout();
  refresh();
})();
