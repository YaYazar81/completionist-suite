// Eigene und angepasste Tiptap-Knoten fuer CompletionistMD.
//
// Jeder Knoten liest genau das HTML, das assets/editor/markdown.js erzeugt,
// und serialize.js schreibt ihn wieder als Markdown. Was hier an Attributen
// steht, ist also das Modell des Markdown-Dialekts.

import { Node, mergeAttributes, nodeInputRule } from "@tiptap/core";
import CodeBlock from "@tiptap/extension-code-block";
import HardBreak from "@tiptap/extension-hard-break";
import Image from "@tiptap/extension-image";
import { TableCell, TableHeader } from "@tiptap/extension-table";

// ------------------------------------------------------------------------
// Bildpfade: im Dokument steht der Markdown-Pfad (relativ zur .md); angezeigt
// wird er aufgeloest gegen den Ordner der Datei.
// ------------------------------------------------------------------------

let base = "";

export function setBase(url) {
  base = url || "";
  if (base && !base.endsWith("/")) base += "/";
}

export function resolveSrc(src) {
  if (!src) return "";
  if (/^(file|https?|data|qrc):/i.test(src)) return src;
  if (/^[A-Za-z]:[\\/]/.test(src)) return "file:///" + src.replace(/\\/g, "/");
  return base + src.replace(/\\/g, "/").replace(/^\.\//, "");
}

const ALIGNS = { left: "left", right: "right", center: "center", middle: "center", none: "center" };

const srcAttr = {
  default: null,
  // data-md-src gewinnt: beim Kopieren innerhalb des Editors steht in src
  // schon der aufgeloeste file://-Pfad.
  parseHTML: (el) => el.getAttribute("data-md-src") || el.getAttribute("src"),
  renderHTML: (a) => ({ src: resolveSrc(a.src), "data-md-src": a.src }),
};

// ------------------------------------------------------------------------
// Bild im Blockfluss: zentriert oder links/rechts umflossen
// ------------------------------------------------------------------------

export const BlockImage = Image.extend({
  name: "image",
  inline: false,
  group: "block",
  draggable: true,

  addOptions() {
    return { ...this.parent?.(), inline: false, allowBase64: false };
  },

  addAttributes() {
    return {
      src: srcAttr,
      alt: { default: "" },
      title: { default: null },
      align: {
        default: "center",
        parseHTML: (el) =>
          ALIGNS[String(el.getAttribute("data-align") || el.getAttribute("align") || "").toLowerCase()] ||
          "center",
        renderHTML: (a) => ({ "data-align": a.align, class: `cm-img cm-align-${a.align}` }),
      },
      width: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-width") || el.getAttribute("width") || "",
        renderHTML: (a) => (a.width ? { "data-width": a.width, style: `width:${a.width}` } : {}),
      },
    };
  },

  parseHTML() {
    return [
      { tag: "img[src]:not([data-inline])" },
      // Bildunterschriften alter Dateien stecken im alt-Text, nicht im Fluss.
      { tag: "figcaption", ignore: true },
    ];
  },
});

// Bild mitten im Satz (![x](y) zwischen Text) -- selten, aber erhaltenswert.
export const InlineImage = Node.create({
  name: "inlineImage",
  inline: true,
  group: "inline",
  atom: true,
  draggable: true,

  addAttributes() {
    return { src: srcAttr, alt: { default: "" } };
  },

  parseHTML() {
    return [{ tag: "img[data-inline]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["img", mergeAttributes(HTMLAttributes, { class: "cm-img cm-inline-img", "data-inline": "1" })];
  },
});

// ------------------------------------------------------------------------
// Trennlinien: *** (hart = Seitenumbruch im PDF) und --- (nur Optik)
// ------------------------------------------------------------------------

export const Rule = Node.create({
  name: "rule",
  group: "block",
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      kind: {
        default: "rule",
        parseHTML: (el) => (el.getAttribute("data-kind") === "break" ? "break" : "rule"),
        renderHTML: (a) => ({
          "data-kind": a.kind,
          class: a.kind === "break" ? "cm-break" : "cm-rule",
        }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "hr" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["hr", HTMLAttributes];
  },

  addCommands() {
    return {
      insertRule:
        (kind) =>
        ({ chain }) =>
          chain().insertContent({ type: this.name, attrs: { kind } }).run(),
    };
  },

  addInputRules() {
    return [
      nodeInputRule({ find: /^(?:---|—-|___\s)$/, type: this.type, getAttributes: { kind: "rule" } }),
      nodeInputRule({ find: /^\*\*\*\s$/, type: this.type, getAttributes: { kind: "break" } }),
    ];
  },
});

// ------------------------------------------------------------------------
// Weiche Umbrueche: eine Zeile im Markdown, kein "  \n"
// ------------------------------------------------------------------------

export const Break = HardBreak.extend({
  addAttributes() {
    return {
      soft: {
        default: false,
        parseHTML: (el) => el.hasAttribute("data-soft"),
        renderHTML: (a) => (a.soft ? { "data-soft": "1" } : {}),
      },
    };
  },
});

// ------------------------------------------------------------------------
// Codeblock mit Sprache aus data-lang
// ------------------------------------------------------------------------

export const Code = CodeBlock.extend({
  addAttributes() {
    return {
      language: {
        default: null,
        parseHTML: (el) => {
          const lang = el.getAttribute("data-lang");
          if (lang) return lang;
          const m = /language-(\S+)/.exec(el.querySelector("code")?.className || "");
          return m ? m[1] : null;
        },
        renderHTML: (a) => (a.language ? { "data-lang": a.language } : {}),
      },
    };
  },
});

// ------------------------------------------------------------------------
// HTML-Bloecke, die der Editor nicht versteht: unveraendert durchreichen
// ------------------------------------------------------------------------

export const RawHtml = Node.create({
  name: "rawHtml",
  group: "block",
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      raw: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-raw-html") || "",
        renderHTML: (a) => ({ "data-raw-html": a.raw }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "div[data-raw-html]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { class: "cm-html", contenteditable: "false" }),
      ["span", { class: "cm-html-tag" }, "HTML"],
      ["pre", {}, node.attrs.raw],
    ];
  },
});

// ------------------------------------------------------------------------
// Tabellenzellen mit Spaltenausrichtung
// ------------------------------------------------------------------------

const alignAttr = {
  align: {
    default: "left",
    parseHTML: (el) => el.getAttribute("data-align") || el.style.textAlign || "left",
    renderHTML: (a) => ({ "data-align": a.align, style: `text-align:${a.align}` }),
  },
};

export const Cell = TableCell.extend({
  addAttributes() {
    return { ...this.parent?.(), ...alignAttr };
  },
});

export const Header = TableHeader.extend({
  addAttributes() {
    return { ...this.parent?.(), ...alignAttr };
  },
});
