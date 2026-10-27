// Suchen und Ersetzen sowie die Gliederung (Ueberschriften) fuer die
// Seitenleiste. Python ruft die Funktionen ueber window.CM auf (main.js).
//
// Gesucht wird je Textblock (Absatz, Ueberschrift, Zelle ...) im sichtbaren
// Text -- Treffer duerfen also ueber Formatierungsgrenzen gehen ("**fe**tt").

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey, TextSelection } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

const key = new PluginKey("cmSearch");

export const Search = Extension.create({
  name: "cmSearch",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key,
        state: {
          init: () => ({ matches: [], index: -1 }),
          apply(tr, value) {
            const meta = tr.getMeta(key);
            if (meta) return meta;
            if (!tr.docChanged || !value.matches.length) return value;
            // Treffer mitwandern lassen; neu gesucht wird beim naechsten find()
            const matches = value.matches
              .map((m) => ({ from: tr.mapping.map(m.from), to: tr.mapping.map(m.to, -1) }))
              .filter((m) => m.to > m.from);
            return { matches, index: Math.min(value.index, matches.length - 1) };
          },
        },
        props: {
          decorations(state) {
            const { matches, index } = key.getState(state);
            if (!matches.length) return null;
            return DecorationSet.create(
              state.doc,
              matches.map((m, i) =>
                Decoration.inline(m.from, m.to, { class: i === index ? "cm-find cm-find-current" : "cm-find" })
              )
            );
          },
        },
      }),
    ];
  },
});

function findAll(doc, query, caseSensitive) {
  if (!query) return [];
  const needle = caseSensitive ? query : query.toLowerCase();
  const out = [];
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true;
    let text = "";
    const map = []; // Zeichenindex -> Dokumentposition
    node.forEach((child, offset) => {
      const start = pos + 1 + offset;
      if (child.isText) {
        for (let i = 0; i < child.text.length; i++) map.push(start + i);
        text += child.text;
      } else {
        map.push(start);
        text += "￼"; // Bild o. Ae. -- trifft nie
      }
    });
    const hay = caseSensitive ? text : text.toLowerCase();
    let at = hay.indexOf(needle);
    while (at >= 0) {
      const last = at + needle.length - 1;
      out.push({ from: map[at], to: map[last] + 1 });
      at = hay.indexOf(needle, at + Math.max(1, needle.length));
    }
    return false;
  });
  return out;
}

function show(editor, matches, index) {
  const tr = editor.state.tr.setMeta(key, { matches, index });
  if (index >= 0) {
    const m = matches[index];
    tr.setSelection(TextSelection.create(tr.doc, m.from, m.to)).scrollIntoView();
  }
  editor.view.dispatch(tr);
  return { count: matches.length, index };
}

let last = { query: "", caseSensitive: false };

export function find(editor, query, caseSensitive) {
  last = { query, caseSensitive: !!caseSensitive };
  const matches = findAll(editor.state.doc, query, !!caseSensitive);
  // erster Treffer ab dem Cursor
  const from = editor.state.selection.from;
  let index = matches.findIndex((m) => m.from >= from);
  if (index < 0) index = matches.length ? 0 : -1;
  return show(editor, matches, index);
}

export function findNext(editor, dir) {
  const st = key.getState(editor.state);
  let matches = st.matches;
  if (!matches.length) matches = findAll(editor.state.doc, last.query, last.caseSensitive);
  if (!matches.length) return show(editor, [], -1);
  const index = ((st.index < 0 ? 0 : st.index + (dir < 0 ? -1 : 1)) + matches.length) % matches.length;
  return show(editor, matches, index);
}

export function replace(editor, text) {
  const st = key.getState(editor.state);
  if (st.index < 0 || !st.matches.length) return findNext(editor, 1);
  const m = st.matches[st.index];
  editor.view.dispatch(editor.state.tr.insertText(text, m.from, m.to));
  // neu suchen und beim naechsten Treffer hinter der Ersetzung weitermachen
  const matches = findAll(editor.state.doc, last.query, last.caseSensitive);
  const after = m.from + text.length;
  let index = matches.findIndex((x) => x.from >= after);
  if (index < 0) index = matches.length ? 0 : -1;
  return show(editor, matches, index);
}

export function replaceAll(editor, text) {
  const matches = findAll(editor.state.doc, last.query, last.caseSensitive);
  if (!matches.length) return { count: 0, index: -1, replaced: 0 };
  const tr = editor.state.tr;
  for (let i = matches.length - 1; i >= 0; i--) tr.insertText(text, matches[i].from, matches[i].to);
  tr.setMeta(key, { matches: [], index: -1 });
  editor.view.dispatch(tr);
  return { count: 0, index: -1, replaced: matches.length };
}

export function clearFind(editor) {
  editor.view.dispatch(editor.state.tr.setMeta(key, { matches: [], index: -1 }));
}

// ------------------------------------------------------------------------
// Gliederung
// ------------------------------------------------------------------------

// Je Dokumentstand gemerkt: Scrollen fragt bei jedem Halt nach der aktuellen
// Ueberschrift, das soll nicht jedes Mal den ganzen Guide durchgehen.
const outlineCache = new WeakMap();

export function outline(editor) {
  const doc = editor.state.doc;
  let items = outlineCache.get(doc);
  if (items) return items;
  items = [];
  outlineCache.set(doc, items);
  doc.descendants((node, pos) => {
    if (node.type.name === "heading") {
      // Aufgeklappte Syntax ("## " am Cursor) gehoert nicht in den Titel
      const text = node.textContent.replace(/^#{1,6}\s+/, "").trim();
      items.push({ level: node.attrs.level, text: text || "(ohne Titel)", pos });
      return false;
    }
    return node.isBlock;
  });
  return items;
}

export function gotoPos(editor, pos) {
  const doc = editor.state.doc;
  const at = Math.min(Math.max(0, pos + 1), doc.content.size);
  const tr = editor.state.tr.setSelection(TextSelection.near(doc.resolve(at)));
  editor.view.dispatch(tr);
  editor.view.focus();
  // Ueberschrift an den oberen Rand statt nur "irgendwie sichtbar"
  const dom = editor.view.nodeDOM(pos);
  if (!dom || !dom.scrollIntoView) return;
  // Weite Spruenge sofort: Bloecke ausserhalb des Sichtfelds haben bis zum
  // ersten Anzeigen nur eine geschaetzte Hoehe (content-visibility in
  // editor.css), ein weicher Bildlauf landete daneben. Nach dem ersten Bild
  // stehen die echten Hoehen fest -- dann noch einmal genau ausrichten.
  const far = Math.abs(dom.getBoundingClientRect().top) > 2 * window.innerHeight;
  dom.scrollIntoView({ block: "start", behavior: far ? "instant" : "smooth" });
  if (far) requestAnimationFrame(() => dom.scrollIntoView({ block: "start", behavior: "instant" }));
}
