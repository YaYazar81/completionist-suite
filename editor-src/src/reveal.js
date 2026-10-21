// Render-in-Place (Typora-Stil): Formatiertes zeigt seine Markdown-Syntax,
// sobald der Cursor darin steht, und laesst sie direkt bearbeiten.
//
// Inline (fett, kursiv, durchgestrichen, Code, Links) und Ueberschriften
// werden dabei wirklich zu Text: Beim Betreten setzt der Editor die
// Begrenzer ("**", "## ", "](url)") als echte Zeichen ein und nimmt die
// Formatierung weg, beim Verlassen liest er den Text wieder als Markdown.
// Solcher Quelltext traegt die Markierung "mdSource" -- serialize.js schreibt
// ihn unveraendert, die Datei sieht also in beiden Zustaenden gleich aus.
//
// Damit Rueckgaengig ueber das Auf- und Zuklappen hinweg funktioniert, aendern
// beide Richtungen nur die Begrenzer und die Markierungen; die Zeichen
// dazwischen bleiben dieselben (siehe scan()). Beides laeuft ausserhalb der
// Historie.
//
// Trennlinien werden beim Betreten zu einem Absatz "***" bzw. "---".
// Zitate, Listen und Codebloecke zeigen ihre Marker als Einblendung; die
// Sprache eines Codeblocks ist dort direkt editierbar.

import { Extension, InputRule, Mark } from "@tiptap/core";
import { NodeSelection, Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

import { inlineMarkdown } from "./serialize.js";

const key = new PluginKey("cmReveal");

const SYNTAX = ["bold", "italic", "strike", "code", "link", "underline"];
const RULE_RE = /^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$/;
const HEADING_RE = /^(#{1,6})[ \t]+/;

// ------------------------------------------------------------------------
// Markierung fuer aufgeklappten Quelltext
// ------------------------------------------------------------------------

export const MdSource = Mark.create({
  name: "mdSource",
  inclusive: true,
  // "code": Eingaberegeln (** -> fett usw.) greifen im Quelltext nicht.
  code: true,
  parseHTML() {
    return [];
  },
  renderHTML() {
    return ["span", { class: "cm-src" }, 0];
  },
});

// ------------------------------------------------------------------------
// Inline-Markdown mit Positionen
//
// scan(s) liefert je Zeichen von s entweder null (Syntax, faellt beim
// Zuklappen weg) oder { marks } (bleibt, mit diesen Markierungen). Die
// Regeln folgen MD.inline in assets/editor/markdown.js.
// ------------------------------------------------------------------------

const PUNCT = "\\`*_{}[]()#+-.!|~<>\"'";
const LINK_RE = /^\[((?:[^\[\]\\]|\\.|\[[^\]]*\])*)\]\(\s*(<[^>]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)(?:\s+"([^"]*)")?\s*\)/;

function isWordChar(c) {
  return !!c && /[\w\u00c0-\u024f]/.test(c);
}

export function scan(s) {
  const out = new Array(s.length).fill(null);
  walk(s, 0, s.length, [], out);
  return out;
}

function walk(s, start, end, marks, out) {
  let i = start;
  const keep = (a, b, m) => {
    for (let k = a; k < b; k++) out[k] = { marks: m };
  };
  const wrap = (open, inner, close, mark) => {
    // open/close = Laenge der Begrenzer, inner = Laenge des Inhalts
    walk(s, i + open, i + open + inner, marks.concat(mark), out);
    i += open + inner + close;
  };

  while (i < end) {
    const ch = s[i];
    const rest = s.slice(i, end);
    const prev = i > start ? s[i - 1] : "";
    let m;

    if (ch === "\\" && i + 1 < end && PUNCT.indexOf(s[i + 1]) >= 0) {
      out[i + 1] = { marks };
      i += 2;
      continue;
    }

    if (ch === "&" && (m = /^&amp;/.exec(rest))) {
      out[i] = { marks };
      i += m[0].length;
      continue;
    }

    if (ch === "`" && (m = /^(`+)([\s\S]*?[^`])\1(?!`)/.exec(rest))) {
      const n = m[1].length;
      let a = i + n;
      let b = a + m[2].length;
      if (/^ [\s\S]* $/.test(m[2])) {
        a += 1;
        b -= 1;
      }
      keep(a, b, marks.concat({ name: "code" }));
      i += m[0].length;
      continue;
    }

    if (ch === "[" && (m = LINK_RE.exec(rest))) {
      const href = m[2].replace(/^<|>$/g, "");
      wrap(1, m[1].length, m[0].length - 1 - m[1].length, {
        name: "link",
        attrs: { href, title: m[3] || null },
      });
      continue;
    }

    if (ch === "~" && s[i + 1] === "~" && (m = /^~~(?=\S)([\s\S]*?\S)~~/.exec(rest))) {
      wrap(2, m[1].length, 2, { name: "strike" });
      continue;
    }

    if (ch === "*" || ch === "_") {
      const e = "\\" + ch;
      if (rest.slice(0, 2) === ch + ch) {
        m = new RegExp("^" + e + e + "(?=\\S)([\\s\\S]*?\\S)" + e + e).exec(rest);
        if (m && (ch === "*" || !isWordChar(prev))) {
          wrap(2, m[1].length, 2, { name: "bold" });
          continue;
        }
      }
      m = new RegExp("^" + e + "(?=\\S)([\\s\\S]*?\\S)" + e + "(?!" + e + ")").exec(rest);
      if (m && (ch === "*" || (!isWordChar(prev) && !isWordChar(s[i + m[0].length])))) {
        wrap(1, m[1].length, 1, { name: "italic" });
        continue;
      }
    }

    if (ch === "<" && (m = /^<u>([\s\S]*?)<\/u>/i.exec(rest))) {
      wrap(3, m[1].length, 4, { name: "underline" });
      continue;
    }

    out[i] = { marks };
    i += 1;
  }
}

// ------------------------------------------------------------------------
// Hilfen
// ------------------------------------------------------------------------

function hasSource(node, schema) {
  return !!node && node.isText && !!schema.marks.mdSource.isInSet(node.marks);
}

/** Alle zusammenhaengenden Quelltext-Laeufe im Dokument. */
function findRegions(doc, schema) {
  const regions = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    let cur = null;
    node.forEach((child, offset) => {
      const p = pos + 1 + offset;
      if (hasSource(child, schema)) {
        if (cur && cur.to === p) cur.to = p + child.nodeSize;
        else {
          cur = { from: p, to: p + child.nodeSize, block: pos };
          regions.push(cur);
        }
      } else cur = null;
    });
    return false;
  });
  return regions;
}

/** Zusammenhaengender Bereich formatierten Texts um pos -- nie mitten in einer Markierung. */
function markRangeAround(doc, pos) {
  const $pos = doc.resolve(pos);
  const parent = $pos.parent;
  if (!parent.isTextblock || parent.type.spec.code) return null;
  const start = $pos.start();
  const kids = [];
  parent.forEach((n, off) => kids.push({ n, from: start + off, to: start + off + n.nodeSize }));
  const syntaxMarks = (n) => n.marks.filter((mk) => SYNTAX.includes(mk.type.name));

  let lo = -1;
  let hi = -1;
  kids.forEach((k, i) => {
    if (k.n.isText && syntaxMarks(k.n).length && k.from <= pos && pos <= k.to) {
      if (lo < 0) lo = i;
      hi = i;
    }
  });
  if (lo < 0) return null;

  for (let changed = true; changed; ) {
    changed = false;
    const inside = [];
    for (let i = lo; i <= hi; i++) inside.push(...syntaxMarks(kids[i].n));
    const shares = (k) => k && syntaxMarks(k.n).some((mk) => inside.some((o) => o.eq(mk)));
    if (shares(kids[lo - 1])) {
      lo--;
      changed = true;
    }
    if (shares(kids[hi + 1])) {
      hi++;
      changed = true;
    }
  }
  return { from: kids[lo].from, to: kids[hi].to };
}

function touches(sel, r) {
  return sel.head >= r.from && sel.head <= r.to;
}

function makeMark(schema, spec) {
  const type = schema.marks[spec.name];
  return type ? type.create(spec.attrs || null) : null;
}

// ------------------------------------------------------------------------
// Aufklappen / Zuklappen
// ------------------------------------------------------------------------

function revealInline(tr, from, to, schema) {
  const src = schema.marks.mdSource.create();
  let plain = "";
  let ok = true;
  tr.doc.nodesBetween(from, to, (node, pos) => {
    if (node.isText) {
      plain += node.text.slice(Math.max(from, pos) - pos, Math.min(to, pos + node.nodeSize) - pos);
    } else if (node.isInline) ok = false;
    return true;
  });
  if (!ok) return false;

  const fake = schema.nodes.paragraph.create(null, tr.doc.slice(from, to).content);
  const md = inlineMarkdown(fake);
  const res = scan(md);

  // Einfuegungen relativ zum Klartext sammeln und dabei pruefen, dass die
  // behaltenen Zeichen genau den Klartext ergeben.
  const inserts = [];
  let kept = "";
  let run = "";
  for (let i = 0; i < md.length; i++) {
    if (res[i]) {
      if (run) inserts.push({ at: kept.length, text: run });
      run = "";
      kept += md[i];
    } else run += md[i];
  }
  if (run) inserts.push({ at: kept.length, text: run });
  if (kept !== plain || !inserts.length) return false;

  for (const name of SYNTAX) {
    if (schema.marks[name]) tr.removeMark(from, to, schema.marks[name]);
  }
  for (let k = inserts.length - 1; k >= 0; k--) {
    tr.insert(from + inserts[k].at, schema.text(inserts[k].text, [src]));
  }
  const total = inserts.reduce((n, x) => n + x.text.length, 0);
  tr.addMark(from, to + total, src);
  return true;
}

function collapseInline(tr, from, to, schema) {
  const srcType = schema.marks.mdSource;
  const $from = tr.doc.resolve(from);
  const parent = $from.parent;
  const text = tr.doc.textBetween(from, to, "\ufffc", "\ufffc");

  // Ein ganzer Absatz "***" / "---" wird wieder zur Trennlinie.
  if (
    parent.type.name === "paragraph" &&
    from === $from.start() &&
    to === $from.end() &&
    RULE_RE.test(text)
  ) {
    const kind = text.trim()[0] === "*" ? "break" : "rule";
    tr.replaceWith($from.before(), $from.after(), schema.nodes.rule.create({ kind }));
    return;
  }

  // Vorhandene Markierungen je Zeichen merken (z. B. Strg+B im Quelltext).
  const extra = [];
  tr.doc.nodesBetween(from, to, (node, pos) => {
    if (!node.isText) return true;
    const a = Math.max(from, pos);
    const b = Math.min(to, pos + node.nodeSize);
    const ms = node.marks.filter((mk) => mk.type !== srcType);
    for (let p = a; p < b; p++) extra[p - from] = ms;
    return true;
  });

  const res = scan(text);
  tr.removeMark(from, to, srcType);
  // Markierungen laufweise setzen: gleiche Zeichen hintereinander -> ein Schritt.
  const marksAt = (i) =>
    res[i] ? res[i].marks.map((s) => makeMark(schema, s)).filter(Boolean).concat(extra[i] || []) : null;
  const same = (a, b) => a && b && a.length === b.length && a.every((mk, k) => mk.eq(b[k]));
  for (let i = 0; i < text.length; ) {
    const ms = marksAt(i);
    let j = i + 1;
    while (ms && j < text.length && same(ms, marksAt(j))) j++;
    if (ms) for (const mk of ms) tr.addMark(from + i, from + j, mk);
    i = j;
  }
  // Syntaxzeichen von hinten nach vorn entfernen, damit Positionen stimmen.
  for (let i = text.length - 1; i >= 0; ) {
    if (res[i]) {
      i--;
      continue;
    }
    let j = i;
    while (j > 0 && !res[j - 1]) j--;
    tr.delete(from + j, from + i + 1);
    i = j - 1;
  }
}

function revealHeading(tr, pos, schema) {
  const node = tr.doc.nodeAt(pos);
  if (!node || node.type.name !== "heading") return false;
  const first = node.firstChild;
  if (hasSource(first, schema) && HEADING_RE.test(node.textContent)) return true;
  const prefix = "#".repeat(node.attrs.level) + " ";
  tr.insert(pos + 1, schema.text(prefix, [schema.marks.mdSource.create()]));
  return true;
}

/** Laenge des "## "-Praefixes aus Quelltext am Anfang einer Ueberschrift. */
function headingPrefix(node, schema) {
  let raw = "";
  node.forEach((child) => {
    if (raw !== null && hasSource(child, schema)) raw += child.text;
    else raw = raw || null;
  });
  if (!raw) return null;
  const m = HEADING_RE.exec(raw);
  return m ? { len: m[0].length, level: m[1].length } : { len: 0, level: 0, raw };
}

function collapseHeading(tr, pos, schema) {
  const node = tr.doc.nodeAt(pos);
  if (!node || node.type.name !== "heading") return;
  const p = headingPrefix(node, schema);
  if (p && p.len) {
    tr.delete(pos + 1, pos + 1 + p.len);
    if (p.level !== node.attrs.level) tr.setNodeMarkup(pos, null, { ...node.attrs, level: p.level });
    return;
  }
  // Rauten geloescht oder ungueltig ("##Titel", "#######"): normaler Absatz.
  tr.setNodeMarkup(pos, schema.nodes.paragraph);
}

function revealRule(tr, pos, schema) {
  const node = tr.doc.nodeAt(pos);
  if (!node || node.type.name !== "rule") return false;
  const text = node.attrs.kind === "break" ? "***" : "---";
  const para = schema.nodes.paragraph.create(null, schema.text(text, [schema.marks.mdSource.create()]));
  tr.replaceWith(pos, pos + node.nodeSize, para);
  tr.setSelection(TextSelection.create(tr.doc, pos + 1 + text.length));
  return true;
}

// ------------------------------------------------------------------------
// Plugin
// ------------------------------------------------------------------------

function headingPosAt(sel) {
  const $h = sel.$head;
  return $h.parent.type.name === "heading" ? $h.before() : null;
}

function revealPlugin(editor) {
  return new Plugin({
    key,
    state: {
      init: () => ({ focused: true, idle: true, heading: null }),
      apply(tr, prev) {
        const meta = tr.getMeta(key) || {};
        let heading = prev.heading;
        if (heading !== null) {
          const r = tr.mapping.mapResult(heading, 1);
          heading = r.deleted ? null : r.pos;
        }
        if ("heading" in meta) heading = meta.heading;
        const focused = "focused" in meta ? meta.focused : prev.focused;
        let idle = prev.idle;
        if ("idle" in meta) idle = meta.idle;
        else if ((tr.docChanged || tr.selectionSet) && !meta.internal) idle = false;
        return { focused, idle, heading };
      },
    },

    appendTransaction(trs, oldState, newState) {
      if (trs.some((t) => t.getMeta("cmNoReveal"))) return null;
      const st = key.getState(newState);
      const schema = newState.schema;
      const tr = newState.tr;
      let heading = st.heading;
      const active = st.focused && !st.idle && editor.isEditable;

      // Was der Nutzer direkt neben Quelltext tippt oder einfuegt, gehoert dazu.
      const srcType = schema.marks.mdSource;
      const inserted = [];
      trs.forEach((t, idx) => {
        if (!t.docChanged || t.getMeta(key)) return;
        const undo = !!t.getMeta("history$");
        const rest = trs.slice(idx + 1);
        t.mapping.maps.forEach((map, mi) => {
          map.forEach((_oa, _ob, nFrom, nTo) => {
            let a = nFrom;
            let b = nTo;
            for (let k = mi + 1; k < t.mapping.maps.length; k++) {
              a = t.mapping.maps[k].map(a, -1);
              b = t.mapping.maps[k].map(b, 1);
            }
            rest.forEach((r) => {
              a = r.mapping.map(a, -1);
              b = r.mapping.map(b, 1);
            });
            if (b <= a || b > tr.doc.content.size) return;
            const $a = tr.doc.resolve(a);
            const $b = tr.doc.resolve(b);
            if ($a.parent !== $b.parent || !$a.parent.isTextblock || $a.parent.type.spec.code) return;
            inserted.push({ a, b, undo });
          });
        });
      });
      // Von hinten, weil das Aufklappen Positionen dahinter verschiebt.
      inserted.sort((x, y) => y.a - x.a);
      for (const { a, b, undo } of inserted) {
        let from = a;
        let to = b;
        if (undo) {
          // Rueckgaengig stellt geloeschte Syntaxzeichen wieder her -- dann den
          // formatierten Text daneben wieder aufklappen, damit "**" Syntax ist
          // und nicht als Text "\*\*" endet.
          const after = markRangeAround(tr.doc, to);
          if (after && after.from >= to && revealInline(tr, after.from, after.to, schema)) {
            // Positionen davor bleiben gleich.
          }
          const before = markRangeAround(tr.doc, from);
          if (before && before.to <= from) {
            const mark = tr.steps.length;
            if (revealInline(tr, before.from, before.to, schema)) {
              const m = tr.mapping.slice(mark);
              from = m.map(from, 1);
              to = m.map(to, 1);
            }
          }
        }
        const $a = tr.doc.resolve(from);
        const $b = tr.doc.resolve(to);
        if (hasSource($a.nodeBefore, schema) || hasSource($b.nodeAfter, schema)) {
          tr.addMark(from, to, srcType.create());
        }
      }

      // 1. Ueberschrift verlassen -> "## " wieder zur Ebene machen.
      if (heading !== null && (!active || headingPosAt(tr.selection) !== heading)) {
        collapseHeading(tr, heading, schema);
        heading = null;
      } else if (heading !== null) {
        // Live: "###" getippt -> sofort Ebene 3 anzeigen.
        const node = tr.doc.nodeAt(heading);
        const p = node && node.type.name === "heading" ? headingPrefix(node, schema) : null;
        if (p && p.len && p.level !== node.attrs.level) {
          tr.setNodeMarkup(heading, null, { ...node.attrs, level: p.level });
        }
      }

      // 2. Quelltext ohne Cursor zuklappen (von hinten, damit Positionen halten).
      const stepsBefore = tr.steps.length;
      const regions = findRegions(tr.doc, schema);
      for (let k = regions.length - 1; k >= 0; k--) {
        const r = { ...regions[k] };
        if (heading !== null && r.block === heading) {
          // Das "## " bleibt, solange der Cursor in der Ueberschrift steht.
          const node = tr.doc.nodeAt(heading);
          const p = headingPrefix(node, schema);
          if (r.from === heading + 1 && p && p.len) r.from += p.len;
          if (r.from >= r.to) continue;
        }
        if (active && touches(tr.selection, r)) continue;
        const block = tr.doc.nodeAt(r.block);
        if (block.type.name === "heading" && r.from === r.block + 1 && r.block !== heading) {
          // Praefix ohne gemerkte Ueberschrift (z. B. nach Rueckgaengig): trotzdem als Ebene lesen.
          const mark = tr.steps.length;
          collapseHeading(tr, r.block, schema);
          r.from = r.block + 1;
          r.to = tr.mapping.slice(mark).map(r.to, -1);
          if (r.from >= r.to) continue;
        }
        collapseInline(tr, r.from, r.to, schema);
      }
      if (heading !== null) heading = tr.mapping.slice(stepsBefore).map(heading, 1);

      // 3. Aufklappen, was unter dem Cursor liegt.
      if (active) {
        const sel = tr.selection;
        if (sel instanceof NodeSelection && sel.node.type.name === "rule") {
          revealRule(tr, sel.from, schema);
        } else if (sel instanceof TextSelection) {
          const hp = headingPosAt(sel);
          if (hp !== null && hp !== heading && revealHeading(tr, hp, schema)) heading = hp;
          const inSource = findRegions(tr.doc, schema).some((r) => touches(tr.selection, r));
          if (sel.empty && !inSource) {
            const range = markRangeAround(tr.doc, tr.selection.head);
            if (range) revealInline(tr, range.from, range.to, schema);
          }
        }
      }

      if (!tr.docChanged && heading === st.heading && tr.selection.eq(newState.selection)) return null;
      tr.setMeta(key, { heading, internal: true });
      tr.setMeta("addToHistory", false);
      return tr;
    },

    props: {
      decorations: (state) => decorations(state),
      handleDOMEvents: {
        focus(view) {
          view.dispatch(view.state.tr.setMeta(key, { focused: true, internal: true }));
          return false;
        },
        blur(view, event) {
          // Fokus wandert nur in ein Feld im Editor (Sprache am Codeblock).
          if (event.relatedTarget && view.dom.contains(event.relatedTarget)) return false;
          view.dispatch(view.state.tr.setMeta(key, { focused: false, internal: true }));
          return false;
        },
      },
    },
  });
}

/** Nach setMarkdown: nichts aufklappen, bis der Nutzer etwas tut. */
export function markIdle(tr) {
  return tr.setMeta(key, { idle: true, internal: true });
}

// ------------------------------------------------------------------------
// Darstellung
// ------------------------------------------------------------------------

function decorations(state) {
  const st = key.getState(state);
  const schema = state.schema;
  const decos = [];

  // Quelltext: Syntax grau, Inhalt schon so formatiert, wie er gelesen wird.
  for (const r of findRegions(state.doc, schema)) {
    const block = state.doc.nodeAt(r.block);
    const text = state.doc.textBetween(r.from, r.to, "\ufffc", "\ufffc");
    let off = 0;
    if (block.type.name === "heading" && r.from === r.block + 1) {
      const m = HEADING_RE.exec(text) || /^#{1,6}/.exec(text);
      if (m) off = m[0].length;
    }
    if (block.type.name === "paragraph" && RULE_RE.test(text) && r.from === r.block + 1) {
      decos.push(Decoration.inline(r.from, r.to, { class: "cm-syn cm-syn-rule" }));
      continue;
    }
    if (off) decos.push(Decoration.inline(r.from, r.from + off, { class: "cm-syn" }));
    const res = scan(text.slice(off));
    let runStart = 0;
    let runCls = null;
    const flush = (end) => {
      if (runCls && end > runStart) {
        decos.push(Decoration.inline(r.from + off + runStart, r.from + off + end, { class: runCls }));
      }
    };
    for (let i = 0; i <= res.length; i++) {
      const cls =
        i === res.length
          ? null
          : res[i]
            ? res[i].marks.map((s) => "cm-r-" + s.name).join(" ") || ""
            : "cm-syn";
      if (cls !== runCls) {
        flush(i);
        runStart = i;
        runCls = cls;
      }
    }
  }

  // Blockmarker nur fuer den Block mit dem Cursor und nur mit Fokus.
  const sel = state.selection;
  if (st.focused && !st.idle && sel instanceof TextSelection) {
    const $h = sel.$head;
    const tb = $h.parent;
    const tbStart = $h.start();
    let prefix = "";
    for (let d = 1; d < $h.depth; d++) {
      const n = $h.node(d);
      const firstChild = $h.index(d) === 0;
      if (n.type.name === "blockquote") prefix += "> ";
      if ((n.type.name === "listItem" || n.type.name === "taskItem") && d === $h.depth - 1 && firstChild) {
        const list = $h.node(d - 1);
        let marker = "- ";
        if (n.type.name === "taskItem") marker = `- [${n.attrs.checked ? "x" : " "}] `;
        else if (list.type.name === "orderedList") marker = (list.attrs.start || 1) + $h.index(d - 1) + ". ";
        decos.push(Decoration.node($h.before(d), $h.after(d), { class: "cm-reveal-li" }));
        prefix += marker;
      }
    }
    if (prefix && tb.isTextblock && !tb.type.spec.code) {
      decos.push(
        Decoration.widget(tbStart, () => syntaxSpan(prefix, "cm-syn-block"), {
          side: -1,
          key: "pfx:" + prefix,
          ignoreSelection: true,
        })
      );
    }
    if (tb.type.name === "codeBlock") {
      const pos = $h.before();
      const lang = tb.attrs.language || "";
      decos.push(Decoration.node(pos, $h.after(), { class: "cm-reveal-code" }));
      decos.push(
        Decoration.widget(tbStart, (view) => fenceOpen(view, pos, lang), {
          side: -1,
          key: "fence:" + pos + ":" + lang,
          stopEvent: () => true,
          ignoreSelection: true,
        })
      );
      decos.push(
        Decoration.widget($h.end(), () => syntaxSpan("```", "cm-fence cm-fence-close"), {
          side: 1,
          key: "fence-close",
          ignoreSelection: true,
        })
      );
    }
  }
  return DecorationSet.create(state.doc, decos);
}

function syntaxSpan(text, cls) {
  const el = document.createElement("span");
  el.className = "cm-syn " + cls;
  el.textContent = text;
  el.contentEditable = "false";
  return el;
}

function fenceOpen(view, pos, lang) {
  const el = document.createElement("div");
  el.className = "cm-syn cm-fence cm-fence-open";
  el.contentEditable = "false";
  el.appendChild(document.createTextNode("```"));
  const input = document.createElement("input");
  input.type = "text";
  input.value = lang;
  input.placeholder = "sprache";
  input.spellcheck = false;
  input.className = "cm-fence-lang";
  const commit = (refocus) => {
    const node = view.state.doc.nodeAt(pos);
    const value = input.value.trim() || null;
    if (node && node.type.name === "codeBlock" && value !== (node.attrs.language || null)) {
      view.dispatch(view.state.tr.setNodeMarkup(pos, null, { ...node.attrs, language: value }));
    }
    if (refocus) {
      view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, pos + 1)));
      view.focus();
    }
  };
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === "Escape" || ev.key === "ArrowDown") {
      ev.preventDefault();
      if (ev.key === "Escape") input.value = lang;
      commit(true);
    }
  });
  input.addEventListener("change", () => commit(false));
  el.appendChild(input);
  return el;
}

// ------------------------------------------------------------------------
// Eingaberegeln, die Tiptap nicht mitbringt
// ------------------------------------------------------------------------

function textBeforeMatch(state, from) {
  const $s = state.doc.resolve(from);
  return $s.parentOffset ? $s.parent.textBetween($s.parentOffset - 1, $s.parentOffset) : "";
}

const linkRule = new InputRule({
  find: /\[([^\[\]]+)\]\(([^()\s]+)\)$/,
  handler: ({ state, range, match }) => {
    if (textBeforeMatch(state, range.from) === "!") return null;
    const { tr, schema } = state;
    const mark = schema.marks.link.create({ href: match[2] });
    tr.replaceWith(range.from, range.to, schema.text(match[1], [mark]));
    tr.removeStoredMark(schema.marks.link);
  },
});

const imageRule = new InputRule({
  find: /!\[([^\[\]]*)\]\(([^()\s]+)\)$/,
  handler: ({ state, range, match }) => {
    const { tr, schema } = state;
    const $from = tr.doc.resolve(range.from);
    const parent = $from.parent;
    const whole = parent.type.name === "paragraph" && $from.parentOffset === 0 && range.to >= $from.end();
    if (whole) {
      const img = schema.nodes.image.create({ src: match[2], alt: match[1], align: "center", width: "" });
      tr.replaceWith($from.before(), $from.after(), img);
    } else {
      tr.replaceWith(range.from, range.to, schema.nodes.inlineImage.create({ src: match[2], alt: match[1] }));
    }
  },
});

// "- [ ] " in einer Aufzaehlung: die Liste wird zur Aufgabenliste.
const taskInListRule = new InputRule({
  find: /^\s*\[([ xX]?)\]\s$/,
  handler: ({ state, range, match, chain }) => {
    const $from = state.doc.resolve(range.from);
    if ($from.depth < 3 || $from.node(-1).type.name !== "listItem" || $from.node(-2).type.name !== "bulletList") {
      return null;
    }
    const c = chain().deleteRange(range).toggleList("taskList", "taskItem");
    if (match[1].toLowerCase() === "x") c.updateAttributes("taskItem", { checked: true });
    c.run();
  },
});

/** Enter nach "***", "---", "___" oder "```sprache" am Absatzende. */
function enterRules(editor) {
  const { state } = editor;
  const sel = state.selection;
  if (!sel.empty) return false;
  const $h = sel.$head;
  const para = $h.parent;
  if (para.type.name !== "paragraph" || $h.parentOffset !== para.content.size) return false;
  const text = para.textContent;
  const schema = state.schema;
  const from = $h.before();
  const to = $h.after();

  if (RULE_RE.test(text)) {
    const kind = text.trim()[0] === "*" ? "break" : "rule";
    const tr = state.tr.replaceWith(from, to, [
      schema.nodes.rule.create({ kind }),
      schema.nodes.paragraph.create(),
    ]);
    tr.setSelection(TextSelection.create(tr.doc, from + 2));
    editor.view.dispatch(tr.scrollIntoView());
    return true;
  }
  const m = /^```([\w+#-]*)\s*$/.exec(text);
  if (m) {
    const tr = state.tr.replaceWith(from, to, schema.nodes.codeBlock.create({ language: m[1] || null }));
    tr.setSelection(TextSelection.create(tr.doc, from + 1));
    editor.view.dispatch(tr.scrollIntoView());
    return true;
  }
  return false;
}

export const RenderInPlace = Extension.create({
  name: "renderInPlace",
  priority: 1000,

  addInputRules() {
    return [taskInListRule, imageRule, linkRule];
  },

  addKeyboardShortcuts() {
    return { Enter: ({ editor }) => enterRules(editor) };
  },

  addProseMirrorPlugins() {
    return [revealPlugin(this.editor)];
  },
});
