// CompletionistMD -- Tiptap-Editor im QWebEngineView.
//
// Python spricht ueber window.CM.<name>(...) (runJavaScript) hinein; heraus
// gehen nur kurze Meldungen ueber die Konsolenbruecke (@@CM@@ + JSON), siehe
// mdeditor/webview.py. Den Dokumentinhalt holt Python sich selbst mit
// CM.unsavedMarkdown(), wenn der Auto-Save-Debounce zuschlaegt.
//
// "dirty" heisst: das Markdown weicht vom zuletzt gespeicherten Stand ab.
// Klicks, die nur Syntax auf- und zuklappen (reveal.js), aendern zwar das
// Dokument, aber nicht das Markdown -- sie loesen kein Speichern aus.
//
// Markdown -> Dokument: window.MD.toHtml (assets/editor/markdown.js) erzeugt
// HTML, das die Parse-Regeln in nodes.js lesen. Dokument -> Markdown:
// serialize.js.

import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { Table, TableRow } from "@tiptap/extension-table";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { EditorState, NodeSelection, Selection } from "@tiptap/pm/state";
import { TableMap } from "@tiptap/pm/tables";

import {
  BlockImage,
  Break,
  Cell,
  Code,
  Header,
  InlineImage,
  RawHtml,
  Rule,
  setBase,
} from "./nodes.js";
import { MdSource, RenderInPlace, markIdle } from "./reveal.js";
import { imageMd, serialize } from "./serialize.js";
import { Search, clearFind, find, findNext, gotoPos, outline, replace, replaceAll } from "./search.js";

const MD = window.MD;

let editor = null;
let loading = false;
let savedMd = "";     // Markdown, wie es zuletzt geladen bzw. gespeichert wurde
let reported = false; // "dirty" an Python gemeldet
let imageBar = null;
let imageSrc = null;
let imageKey = "";

function send(obj) {
  console.log("@@CM@@" + JSON.stringify(obj));
}

// ------------------------------------------------------------------------
// Aufbau
// ------------------------------------------------------------------------

function createEditor() {
  editor = new Editor({
    element: document.getElementById("doc"),
    extensions: [
      StarterKit.configure({
        horizontalRule: false, // ersetzt durch Rule (zwei Arten)
        codeBlock: false,      // ersetzt durch Code (Sprache aus data-lang)
        hardBreak: false,      // ersetzt durch Break (weich/hart)
        heading: { levels: [1, 2, 3, 4, 5, 6] },
        link: { openOnClick: false, autolink: true, linkOnPaste: true },
      }),
      Break,
      Code,
      Rule,
      BlockImage,
      InlineImage,
      RawHtml,
      Table.configure({ resizable: false }),
      TableRow,
      Header,
      Cell,
      TaskList,
      TaskItem.configure({ nested: true }),
      MdSource,
      RenderInPlace,
      Search,
    ],
    content: "<p></p>",
    editorProps: {
      attributes: { class: "cm-doc", spellcheck: "false" },
      handlePaste,
      handleDrop,
    },
    onUpdate: () => {
      if (!loading) checkDirty();
      sendOutline();
    },
    onSelectionUpdate: () => sendState(),
    onTransaction: () => updateImageBar(),
  });
}

// ------------------------------------------------------------------------
// Einfuegen / Ablegen
// ------------------------------------------------------------------------

const MD_HINT = /^(#{1,6} |[-*+] |\d+\. |> |\||```|\*\*\*$|---$)/m;

function handlePaste(view, event) {
  const data = event.clipboardData;
  if (!data) return false;
  // Bilder legt Python im Ordner images/ ab -- nie als data-URI. Strg+V
  // erreicht Python nicht immer selbst (QtWebEngine behaelt die Taste fuer
  // sich), deshalb meldet der Editor das Einfuegen ausdruecklich.
  const hasImage = (data.files && data.files.length) ||
    Array.from(data.items || []).some((it) => it.kind === "file" && /^image\//.test(it.type));
  if (hasImage) {
    send({ type: "pasteImage" });
    return true;
  }
  const html = data.getData("text/html");
  const text = data.getData("text/plain");
  if (!html && text && (/\n/.test(text.trim()) || MD_HINT.test(text))) {
    editor.chain().focus().insertContent(MD.toHtml(text)).run();
    return true;
  }
  return false;
}

function handleDrop(view, event) {
  // Dateien uebernimmt Python (mdeditor/webview.py faengt den Drop ab).
  return !!(event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length);
}

// ------------------------------------------------------------------------
// Tabellen: ganze Spalte ausrichten
// ------------------------------------------------------------------------

function alignColumn(align) {
  const { state } = editor;
  const $from = state.selection.$from;
  let d = $from.depth;
  while (d > 0 && $from.node(d).type.name !== "table") d--;
  if (!d) return;
  let cd = $from.depth;
  while (cd > 0 && !/^table(Cell|Header)$/.test($from.node(cd).type.name)) cd--;
  if (!cd) return;

  const table = $from.node(d);
  const start = $from.start(d);
  const map = TableMap.get(table);
  const col = map.findCell($from.before(cd) - start).left;
  const tr = state.tr;
  for (let row = 0; row < map.height; row++) {
    const pos = map.map[row * map.width + col];
    const cell = table.nodeAt(pos);
    if (cell) tr.setNodeMarkup(start + pos, null, { ...cell.attrs, align });
  }
  editor.view.dispatch(tr);
}

// ------------------------------------------------------------------------
// Bilder
// ------------------------------------------------------------------------

function selectedImage() {
  const sel = editor.state.selection;
  if (sel instanceof NodeSelection && /^(image|inlineImage)$/.test(sel.node.type.name)) {
    return sel.node;
  }
  return null;
}

function imageSource(node) {
  if (node.type.name === "image") return imageMd(node.attrs);
  return "![" + (node.attrs.alt || "") + "](" + (node.attrs.src || "") + ")";
}

function updateImageBar() {
  if (!imageBar) return;
  const node = selectedImage();
  if (!node) {
    imageBar.style.display = "none";
    imageKey = "";
    return;
  }
  const dom = editor.view.nodeDOM(editor.state.selection.from);
  if (!dom || !dom.getBoundingClientRect) {
    imageBar.style.display = "none";
    return;
  }
  imageBar.style.display = "flex";
  imageBar.classList.toggle("cm-inline", node.type.name !== "image");
  // Quelltext nur bei einem anderen Bild neu setzen -- nicht beim Tippen darin.
  const key = editor.state.selection.from + "|" + imageSource(node);
  if (key !== imageKey && document.activeElement !== imageSrc) {
    imageSrc.value = imageSource(node);
    imageKey = key;
  }
  const r = dom.getBoundingClientRect();
  const bar = imageBar.getBoundingClientRect();
  let top = r.top - bar.height - 8;
  if (top < 4) top = r.bottom + 8;
  imageBar.style.top = top + "px";
  imageBar.style.left = Math.max(6, Math.min(r.left, window.innerWidth - bar.width - 10)) + "px";
  imageBar.querySelectorAll("[data-align]").forEach((b) => {
    b.classList.toggle("on", b.dataset.align === node.attrs.align);
  });
}

/** Einfuegeposition fuer umflossene Bilder: vor den Absatz, damit er fliesst. */
function floatInsertPos(pos) {
  const $pos = editor.state.doc.resolve(pos);
  for (let d = $pos.depth; d > 0; d--) {
    if ($pos.node(d).isTextblock) return $pos.before(d);
  }
  return pos;
}

function imageOperation(op, arg) {
  const node = selectedImage();
  if (!node) return;
  const type = node.type.name;
  if (op === "align" && type === "image") {
    const align = arg === "left" || arg === "right" ? arg : "center";
    let width = node.attrs.width;
    if (align !== "center" && !width) width = "40%";
    editor.chain().focus().updateAttributes("image", { align, width }).run();
  } else if (op === "width" && type === "image") {
    const cur = parseFloat(node.attrs.width || "50") || 50;
    let next = arg === "+" ? cur + 5 : arg === "-" ? cur - 5 : parseFloat(arg);
    next = Math.max(10, Math.min(100, next || cur));
    editor.chain().focus().updateAttributes("image", { width: next + "%" }).run();
  } else if (op === "alt") {
    editor.chain().focus().updateAttributes(type, { alt: arg || "" }).run();
  } else if (op === "delete") {
    editor.chain().focus().deleteSelection().run();
  }
}

function askAlt() {
  const node = selectedImage();
  if (!node) return;
  const alt = window.prompt("Bildunterschrift / Alternativtext:", node.attrs.alt || "");
  if (alt !== null) imageOperation("alt", alt);
}

/** Quelltext aus der Bildleiste uebernehmen: ![alt](pfad) oder <img ...>. */
function applyImageSource(text) {
  const sel = editor.state.selection;
  const node = selectedImage();
  if (!node) return;
  const pos = sel.from;
  const schema = editor.schema;
  text = text.trim();
  let attrs = null;
  let m;
  if ((m = /^!\[((?:[^\]\\]|\\.)*)\]\(\s*(<[^>]*>|[^\s)]*)\s*\)$/.exec(text))) {
    attrs = { src: m[2].replace(/^<|>$/g, ""), alt: m[1].replace(/\\([\[\]])/g, "$1"), align: "center", width: "" };
  } else if (/^<img\b[^>]*>$/i.test(text)) {
    const img = new DOMParser().parseFromString(text, "text/html").querySelector("img");
    if (img) {
      const align = (img.getAttribute("align") || "center").toLowerCase();
      attrs = {
        src: img.getAttribute("src") || "",
        alt: img.getAttribute("alt") || "",
        align: align === "left" || align === "right" ? align : "center",
        width: img.getAttribute("width") || "",
      };
    }
  }
  const tr = editor.state.tr;
  if (!text) {
    tr.delete(pos, pos + node.nodeSize);
  } else if (attrs && node.type.name === "image") {
    tr.setNodeMarkup(pos, null, { ...node.attrs, ...attrs });
    tr.setSelection(NodeSelection.create(tr.doc, pos));
  } else if (attrs) {
    tr.setNodeMarkup(pos, null, { ...node.attrs, src: attrs.src, alt: attrs.alt });
    tr.setSelection(NodeSelection.create(tr.doc, pos));
  } else if (node.type.name === "image") {
    // Kein Bild mehr: als Absatz mit genau diesem Text weiter.
    tr.replaceWith(pos, pos + node.nodeSize, schema.nodes.paragraph.create(null, schema.text(text)));
  } else {
    tr.replaceWith(pos, pos + node.nodeSize, schema.text(text));
  }
  editor.view.dispatch(tr);
  imageKey = "";
  editor.view.focus();
  sendState();
}

// ------------------------------------------------------------------------
// Kontextmenue: zeigt Python als QMenu, hier nur Auswahl und Lage melden
// ------------------------------------------------------------------------

function onContextMenu(ev) {
  ev.preventDefault();
  const view = editor.view;
  if (!view.dom.contains(ev.target)) return;
  const hit = view.posAtCoords({ left: ev.clientX, top: ev.clientY });
  let kind = "text";
  if (ev.target.tagName === "IMG" && hit && hit.inside >= 0) {
    const node = editor.state.doc.nodeAt(hit.inside);
    if (node && /^(image|inlineImage)$/.test(node.type.name)) {
      view.dispatch(editor.state.tr.setSelection(NodeSelection.create(editor.state.doc, hit.inside)));
      kind = node.type.name === "image" ? "image" : "inlineImage";
    }
  }
  if (kind === "text" && hit) {
    const { from, to } = editor.state.selection;
    // Eine bestehende Markierung behalten, wenn der Klick in ihr liegt.
    if (hit.pos < from || hit.pos > to) editor.commands.setTextSelection(hit.pos);
  }
  editor.commands.focus();
  send({
    type: "contextmenu",
    kind,
    inTable: editor.isActive("table"),
    hasSelection: !editor.state.selection.empty,
    canUndo: editor.can().undo(),
    canRedo: editor.can().redo(),
  });
}

// ------------------------------------------------------------------------
// Zustand fuer die Toolbar
// ------------------------------------------------------------------------

function stats() {
  const doc = editor.state.doc;
  const text = doc.textBetween(0, doc.content.size, " ", " ");
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return { words, chars: text.replace(/\s/g, "").length };
}

function currentState() {
  const is = (name, attrs) => editor.isActive(name, attrs);
  let block = "p";
  if (is("heading")) block = "h" + editor.getAttributes("heading").level;
  else if (is("codeBlock")) block = "pre";
  else if (is("taskList")) block = "task";
  else if (is("orderedList")) block = "ol";
  else if (is("bulletList")) block = "ul";
  else if (is("table")) block = "td";
  const img = selectedImage();
  return {
    type: "state",
    block,
    bold: is("bold"),
    italic: is("italic"),
    strike: is("strike"),
    code: is("code"),
    quote: is("blockquote"),
    inTable: is("table"),
    image: img && img.type.name === "image" ? img.attrs.align : "",
  };
}

// Gliederung fuer die Seitenleiste -- gedrosselt, Tippen soll nicht ruckeln
let outlineTimer = null;
let lastOutline = "";
function sendOutline() {
  clearTimeout(outlineTimer);
  outlineTimer = setTimeout(() => {
    const items = outline(editor);
    const sig = JSON.stringify(items.map((i) => [i.level, i.text]));
    const changed = sig !== lastOutline;
    lastOutline = sig;
    send({ type: "outline", items, changed });
  }, 400);
}

// Weicht das Markdown vom gespeicherten Stand ab? -- kurz gedrosselt, damit
// nicht jede Taste das ganze Dokument serialisiert.
let dirtyTimer = null;
function checkDirty() {
  clearTimeout(dirtyTimer);
  dirtyTimer = setTimeout(() => {
    if (serialize(editor.state.doc) !== savedMd) {
      reported = true;
      send({ type: "dirty" });
    } else if (reported) {
      // z. B. zurueck bis zum gespeicherten Stand
      reported = false;
      send({ type: "clean" });
    }
  }, 80);
}

let stateTimer = null;
function sendState() {
  clearTimeout(stateTimer);
  stateTimer = setTimeout(() => {
    const st = currentState();
    st.stats = stats();
    send(st);
  }, 60);
}

// ------------------------------------------------------------------------
// Oeffentliche API (Aufrufe aus Python)
// ------------------------------------------------------------------------

const api = {};

api.setMarkdown = (md, baseUrl) => {
  setBase(baseUrl);
  loading = true;
  editor.commands.setContent(MD.toHtml(md), { emitUpdate: false });
  // Frischer Zustand = leere Historie: das Laden selbst ist nicht rueckgaengig zu machen.
  editor.view.updateState(
    EditorState.create({ doc: editor.state.doc, plugins: editor.state.plugins, schema: editor.schema })
  );
  loading = false;
  clearTimeout(dirtyTimer);
  savedMd = serialize(editor.state.doc);
  reported = false;
  // Cursor in den ersten Text -- "start" waehlte ein Bild am Dokumentanfang aus.
  // Frisch geladen ist alles gerendert, bis der Nutzer klickt oder tippt.
  const first = Selection.findFrom(editor.state.doc.resolve(0), 1, true);
  const tr = markIdle(editor.state.tr);
  if (first) tr.setSelection(first);
  editor.view.dispatch(tr);
  editor.commands.focus();
  window.scrollTo(0, 0);
  sendState();
  lastOutline = "";
  sendOutline();
};

api.getMarkdown = () => serialize(editor.state.doc);

/** Markdown, falls es vom gespeicherten Stand abweicht -- sonst false
 *  (null bekommt Python auch, wenn das Skript scheitert). */
api.unsavedMarkdown = () => {
  const md = serialize(editor.state.doc);
  return md !== savedMd ? md : false;
};

/** Python hat ``md`` geschrieben: neuer Vergleichsstand. Inzwischen
 *  Getipptes meldet sich danach wieder als "dirty". */
api.markSaved = (md) => {
  savedMd = md;
  reported = false;
  checkDirty();
};

api.setTheme = (theme) => {
  document.documentElement.setAttribute("data-theme", theme === "light" ? "light" : "dark");
};

api.setFontSize = (pt) => {
  document.documentElement.style.setProperty("--cm-font-size", pt + "pt");
};

/** Fokus in den Editor; ``where`` = "start" | "end" setzt zusaetzlich den Cursor. */
api.focusEditor = (where) => editor.commands.focus(where || null);
api.stats = stats;
api.state = currentState;
api.undo = () => editor.chain().focus().undo().run();
api.redo = () => editor.chain().focus().redo().run();
api.deleteSelection = () => editor.chain().focus().deleteSelection().run();
api.selectAll = () => editor.chain().focus().selectAll().run();

api.exec = (cmd, arg) => {
  const c = () => editor.chain().focus();
  switch (cmd) {
    case "bold": c().toggleBold().run(); break;
    case "italic": c().toggleItalic().run(); break;
    case "strikeThrough": c().toggleStrike().run(); break;
    case "underline": c().toggleUnderline().run(); break;
    case "code": c().toggleCode().run(); break;
    case "p": c().setParagraph().run(); break;
    case "h1": case "h2": case "h3": case "h4": case "h5": case "h6":
      c().toggleHeading({ level: +cmd[1] }).run();
      break;
    case "quote": c().toggleBlockquote().run(); break;
    case "ul": c().toggleBulletList().run(); break;
    case "ol": c().toggleOrderedList().run(); break;
    case "task": c().toggleTaskList().run(); break;
    case "codeblock": c().toggleCodeBlock().run(); break;
    case "rule": c().insertRule("rule").run(); break;
    case "break": c().insertRule("break").run(); break;
    case "text": c().insertContent(arg || "").run(); break;
    case "link": {
      const href = (arg && arg.href) || window.prompt("Link-Adresse:", "https://");
      if (href) c().extendMarkRange("link").setLink({ href }).run();
      break;
    }
    case "clear": c().unsetAllMarks().clearNodes().run(); break;
    default: break;
  }
  sendState();
};

api.insertTable = (rows, cols) => {
  editor.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run();
  sendState();
};

/** Bild einfuegen; align ist left | right | center | inline. */
api.insertImage = (src, align, width, point) => {
  align = align || "center";
  let pos = editor.state.selection.from;
  if (point && typeof point.x === "number") {
    const hit = editor.view.posAtCoords({ left: point.x, top: point.y });
    if (hit) pos = hit.pos;
  }
  const node =
    align === "inline"
      ? { type: "inlineImage", attrs: { src, alt: "" } }
      : { type: "image", attrs: { src, alt: "", align, width: width || "" } };
  if (align === "left" || align === "right") pos = floatInsertPos(pos);
  editor.chain().focus().insertContentAt(pos, node).run();

  // Das neue Bild auswaehlen, damit die Bildleiste gleich erscheint.
  const doc = editor.state.doc;
  let found = -1;
  doc.nodesBetween(Math.max(0, pos - 2), Math.min(doc.content.size, pos + 4), (n, p) => {
    if (found < 0 && n.type.name === node.type && n.attrs.src === src) found = p;
  });
  if (found >= 0) editor.view.dispatch(editor.state.tr.setSelection(NodeSelection.create(doc, found)));
  sendState();
};

api.tableOp = (op, arg) => {
  const c = () => editor.chain().focus();
  switch (op) {
    case "rowAbove": c().addRowBefore().run(); break;
    case "rowBelow": c().addRowAfter().run(); break;
    case "colLeft": c().addColumnBefore().run(); break;
    case "colRight": c().addColumnAfter().run(); break;
    case "delRow": c().deleteRow().run(); break;
    case "delCol": c().deleteColumn().run(); break;
    case "toggleHeader": c().toggleHeaderRow().run(); break;
    case "align": alignColumn(arg || "left"); break;
    case "delete": c().deleteTable().run(); break;
    default: break;
  }
  sendState();
};

api.imageOp = (op, arg) => {
  if (op === "alt") askAlt();
  else imageOperation(op, arg);
  sendState();
};

// Suchen/Ersetzen und Gliederung (search.js)
api.find = (query, caseSensitive) => find(editor, query, caseSensitive);
api.findNext = (dir) => findNext(editor, dir);
api.replace = (text) => replace(editor, text);
api.replaceAll = (text) => replaceAll(editor, text);
api.clearFind = () => clearFind(editor);
api.outline = () => outline(editor);
api.gotoPos = (pos) => gotoPos(editor, pos);
/** Selektierten Text (fuer das Suchfeld) */
api.selectedText = () => {
  const { from, to } = editor.state.selection;
  return editor.state.doc.textBetween(from, to, " ");
};

window.CM = api;

// ------------------------------------------------------------------------

function bind() {
  document.addEventListener("contextmenu", onContextMenu);
  window.addEventListener("resize", updateImageBar);
  document.addEventListener("scroll", updateImageBar, true);

  editor.view.dom.addEventListener("dblclick", (ev) => {
    if (ev.target.tagName === "IMG") {
      ev.preventDefault();
      askAlt();
    }
  });

  imageBar.addEventListener("mousedown", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    ev.preventDefault();
    if (b.dataset.align) api.imageOp("align", b.dataset.align);
    else if (b.dataset.width) api.imageOp("width", b.dataset.width);
    else if (b.dataset.act === "alt") askAlt();
    else if (b.dataset.act === "delete") api.imageOp("delete");
  });

  imageSrc.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      applyImageSource(imageSrc.value);
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      imageKey = "";
      editor.view.focus();
      updateImageBar();
    }
  });
  imageSrc.addEventListener("change", () => {
    const node = selectedImage();
    if (node && imageSrc.value.trim() !== imageSource(node)) applyImageSource(imageSrc.value);
  });
}

window.addEventListener("DOMContentLoaded", () => {
  imageBar = document.getElementById("imagebar");
  imageSrc = document.getElementById("imagesrc");
  createEditor();
  bind();
  send({ type: "ready" });
});
