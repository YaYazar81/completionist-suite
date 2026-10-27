/* markdown.js -- Markdown -> HTML fuer den Tiptap-Editor von CompletionistMD.
 *
 * Erzeugt genau die HTML-Struktur, die die Parse-Regeln der Tiptap-Knoten
 * (editor-src/src/nodes.js) erwarten. Die Rueckrichtung (Dokument ->
 * Markdown) arbeitet direkt auf dem ProseMirror-Dokument: src/serialize.js.
 *
 * Dialekt wie CompletionistPDF (markdown-it, CommonMark + Tabellen +
 * Strikethrough + Aufgabenlisten), mit zwei Hausregeln:
 *
 *   ***  -> harte Trennlinie  (CompletionistPDF: Seitenumbruch)
 *   ---  -> visuelle Linie    (nur Optik)
 *
 * Weiche Zeilenumbrueche bleiben als <br data-soft> erhalten -- CompletionistPDF
 * kann sie wahlweise als Zeilenumbruch setzen, sie duerfen also nicht verloren
 * gehen.
 */
(function (global) {
  "use strict";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escAttr(s) {
    return esc(s).replace(/"/g, "&quot;");
  }

  // Inline-HTML, das wir durchlassen (alles andere wird Text).
  var INLINE_TAGS = /^(img|br|b|strong|i|em|u|s|del|strike|code|kbd)$/i;

  function parseAttrs(tag) {
    var attrs = {};
    var re = /([A-Za-z_:][-\w:.]*)\s*(?:=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?/g;
    var body = tag.replace(/^<\s*[A-Za-z][\w-]*/, "").replace(/\/?>$/, "");
    var m;
    while ((m = re.exec(body))) {
      var v = m[2] || "";
      if (/^["']/.test(v)) v = v.slice(1, -1);
      attrs[m[1].toLowerCase()] = v;
    }
    return attrs;
  }

  var ALIGNS = { left: "left", right: "right", center: "center", middle: "center", none: "center" };

  function imageBlockHtml(src, alt, align, width) {
    align = ALIGNS[String(align || "").toLowerCase()] || "center";
    return '<img data-block="1" src="' + escAttr(src) + '" alt="' + escAttr(alt || "") +
      '" data-align="' + align + '"' + (width ? ' data-width="' + escAttr(width) + '"' : "") + ">";
  }

  function inlineImageHtml(src, alt) {
    return '<img data-inline="1" src="' + escAttr(src) + '" alt="' + escAttr(alt || "") + '">';
  }

  /* ------------------------------------------------------------------ */
  /* Inline                                                              */
  /* ------------------------------------------------------------------ */

  var LINK_RE = /^\[((?:[^\[\]\\]|\\.|\[[^\]]*\])*)\]\(\s*(<[^>]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)(?:\s+"([^"]*)")?\s*\)/;

  function isWordChar(c) {
    return !!c && /[\w\u00c0-\u024f]/.test(c);
  }
  function unescapeMd(s) {
    return s.replace(/\\([\\`*_{}\[\]()#+\-.!|~])/g, "$1");
  }

  function inline(src) {
    var out = "";
    var i = 0;
    while (i < src.length) {
      var ch = src[i];
      var rest, m;

      if (ch === "\\" && i + 1 < src.length && "\\`*_{}[]()#+-.!|~<>\"'".indexOf(src[i + 1]) >= 0) {
        out += esc(src[i + 1]);
        i += 2;
        continue;
      }

      // HTML-Entitaeten (&lt; &amp; &#8211; ...) wie markdown-it dekodieren lassen
      if (ch === "&") {
        m = /^&(#\d{1,7}|#x[0-9a-f]{1,6}|[a-z][a-z0-9]{1,31});/i.exec(src.slice(i));
        if (m) {
          out += m[0];
          i += m[0].length;
          continue;
        }
      }

      if (ch === "`") {
        m = /^(`+)([\s\S]*?[^`])\1(?!`)/.exec(src.slice(i));
        if (m) {
          out += "<code>" + esc(m[2].replace(/^ (.*) $/, "$1")) + "</code>";
          i += m[0].length;
          continue;
        }
      }

      if (ch === "!" && src[i + 1] === "[") {
        m = LINK_RE.exec(src.slice(i + 1));
        if (m) {
          out += inlineImageHtml(m[2].replace(/^<|>$/g, ""), unescapeMd(m[1]));
          i += m[0].length + 1;
          continue;
        }
      }

      if (ch === "[") {
        m = LINK_RE.exec(src.slice(i));
        if (m) {
          var href = m[2].replace(/^<|>$/g, "");
          out += '<a href="' + escAttr(href) + '"' +
            (m[3] ? ' title="' + escAttr(m[3]) + '"' : "") + ">" + inline(m[1]) + "</a>";
          i += m[0].length;
          continue;
        }
      }

      if (ch === "~" && src[i + 1] === "~") {
        m = /^~~(?=\S)([\s\S]*?\S)~~/.exec(src.slice(i));
        if (m) {
          out += "<s>" + inline(m[1]) + "</s>";
          i += m[0].length;
          continue;
        }
      }

      if (ch === "*" || ch === "_") {
        rest = src.slice(i);
        if (rest.slice(0, 2) === ch + ch) {
          m = new RegExp("^\\" + ch + "\\" + ch + "(?=\\S)([\\s\\S]*?\\S)\\" + ch + "\\" + ch).exec(rest);
          if (m && (ch === "*" || !isWordChar(src[i - 1]))) {
            out += "<strong>" + inline(m[1]) + "</strong>";
            i += m[0].length;
            continue;
          }
        }
        m = new RegExp("^\\" + ch + "(?=\\S)([\\s\\S]*?\\S)\\" + ch + "(?!\\" + ch + ")").exec(rest);
        if (m && (ch === "*" || (!isWordChar(src[i - 1]) && !isWordChar(src[i + m[0].length])))) {
          out += "<em>" + inline(m[1]) + "</em>";
          i += m[0].length;
          continue;
        }
      }

      if (ch === "<") {
        rest = src.slice(i);
        m = /^<(\/?)([A-Za-z][\w-]*)([^>]*)>/.exec(rest);
        if (m && INLINE_TAGS.test(m[2])) {
          if (/^img$/i.test(m[2])) {
            var a = parseAttrs(m[0]);
            out += inlineImageHtml(a.src || "", a.alt || "");
          } else if (/^br$/i.test(m[2])) {
            out += "<br>";
          } else {
            out += m[0];
          }
          i += m[0].length;
          continue;
        }
        m = /^<((?:https?|mailto):[^>\s]+)>/.exec(rest);
        if (m) {
          out += '<a href="' + escAttr(m[1]) + '">' + esc(m[1]) + "</a>";
          i += m[0].length;
          continue;
        }
      }

      out += esc(ch);
      i += 1;
    }
    return out;
  }

  /* ------------------------------------------------------------------ */
  /* Bloecke                                                             */
  /* ------------------------------------------------------------------ */

  var RE_HEADING = /^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$/;
  var RE_BREAK = /^ {0,3}(\*[ \t]*){3,}$/;
  var RE_RULE = /^ {0,3}((-[ \t]*){3,}|(_[ \t]*){3,})$/;
  var RE_FENCE = /^ {0,3}(```+|~~~+)[ \t]*([\w+#-]*)[ \t]*$/;
  var RE_QUOTE = /^ {0,3}>[ \t]?(.*)$/;
  var RE_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/;
  var RE_EMPTY_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])[ \t]*$/;
  var RE_TASK = /^\[([ xX])\][ \t]+(.*)$/;
  var RE_IMG_BLOCK = /^ {0,3}(<img\b[^>]*>)[ \t]*$/i;
  var RE_HTML_OPEN = /^ {0,3}<([A-Za-z][\w-]*)/;
  var RE_TABLE_SEP = /^ {0,3}\|?[ \t]*:?-{1,}:?[ \t]*(\|[ \t]*:?-{1,}:?[ \t]*)*\|?[ \t]*$/;

  function toHtml(md) {
    var lines = String(md == null ? "" : md).replace(/\r\n?/g, "\n").split("\n");
    return blocks(lines).join("") || "<p></p>";
  }

  function blocks(lines) {
    var out = [];
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      var m;

      if (!line.trim()) { i += 1; continue; }

      if ((m = RE_HEADING.exec(line))) {
        var lvl = m[1].length;
        out.push("<h" + lvl + ">" + inline(m[2]) + "</h" + lvl + ">");
        i += 1;
        continue;
      }

      if (RE_BREAK.test(line)) { out.push('<hr data-kind="break">'); i += 1; continue; }
      if (RE_RULE.test(line)) { out.push('<hr data-kind="rule">'); i += 1; continue; }

      if ((m = RE_FENCE.exec(line))) {
        // Schliessen nur mit mindestens so vielen Zeichen wie beim Oeffnen: ein
        // Codeblock, der selbst ``` enthaelt, wird mit ```` umzaeunt.
        var fence = new RegExp("^ {0,3}" + m[1] + m[1][0] + "*[ \\t]*$");
        var lang = m[2] || "";
        var body = [];
        i += 1;
        while (i < lines.length && !fence.test(lines[i])) { body.push(lines[i]); i += 1; }
        if (i < lines.length) i += 1;
        out.push("<pre" + (lang ? ' data-lang="' + escAttr(lang) + '"' : "") +
          "><code>" + esc(body.join("\n")) + "</code></pre>");
        continue;
      }

      if ((m = RE_IMG_BLOCK.exec(line))) {
        var a = parseAttrs(m[1]);
        out.push(imageBlockHtml(a.src || "", a.alt || "", a.align || "center", a.width || ""));
        i += 1;
        continue;
      }

      // Ein Bild allein in seiner Zeile ist ein Block, kein Fliesstext.
      if (/^ {0,3}!\[/.test(line)) {
        var t = line.trim();
        var only = LINK_RE.exec(t.slice(1));
        if (only && only[0].length === t.length - 1) {
          out.push(imageBlockHtml(only[2].replace(/^<|>$/g, ""), unescapeMd(only[1]), "center", ""));
          i += 1;
          continue;
        }
      }

      if (RE_QUOTE.test(line)) {
        var inner = [];
        while (i < lines.length && (RE_QUOTE.test(lines[i]) || (inner.length && lines[i].trim()))) {
          var q = RE_QUOTE.exec(lines[i]);
          inner.push(q ? q[1] : lines[i]);
          i += 1;
        }
        out.push("<blockquote>" + blocks(inner).join("") + "</blockquote>");
        continue;
      }

      if (RE_ITEM.test(line) || RE_EMPTY_ITEM.test(line)) {
        var res = parseList(lines, i);
        out.push(res.html);
        i = res.next;
        continue;
      }

      if (line.indexOf("|") >= 0 && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1]) &&
          lines[i + 1].indexOf("|") >= 0) {
        var tb = parseTable(lines, i);
        out.push(tb.html);
        i = tb.next;
        continue;
      }

      if (RE_HTML_OPEN.test(line) && !/^ {0,3}<(img|br)\b/i.test(line)) {
        var raw = [];
        while (i < lines.length && lines[i].trim()) { raw.push(lines[i]); i += 1; }
        out.push('<div data-raw-html="' + escAttr(raw.join("\n")) + '"></div>');
        continue;
      }

      var para = [];
      while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) {
        para.push(lines[i].replace(/^ {0,3}/, ""));
        i += 1;
      }
      if (!para.length) { para.push(lines[i].trim()); i += 1; }
      out.push("<p>" + inlineParagraph(para) + "</p>");
    }
    return out;
  }

  function inlineParagraph(para) {
    return para.map(function (l, idx) {
      var hard = /(  +|\\)$/.test(l);
      var text = inline(l.replace(/(\s+|\\)$/, ""));
      if (idx < para.length - 1) text += hard ? "<br>" : '<br data-soft="1">';
      return text;
    }).join("");
  }

  function startsBlock(lines, i) {
    var l = lines[i];
    if (RE_HEADING.test(l) || RE_BREAK.test(l) || RE_RULE.test(l) || RE_FENCE.test(l)) return true;
    if (RE_QUOTE.test(l) || RE_ITEM.test(l) || RE_IMG_BLOCK.test(l)) return true;
    if (RE_HTML_OPEN.test(l) && !/^ {0,3}<(img|br)\b/i.test(l)) return true;
    if (l.indexOf("|") >= 0 && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1])) return true;
    return false;
  }

  /* ---- Listen ---- */

  function parseList(lines, start) {
    var first = RE_ITEM.exec(lines[start]) || RE_EMPTY_ITEM.exec(lines[start]);
    var baseIndent = first[1].length;
    var ordered = /\d/.test(first[2]);
    var items = [];
    var i = start;

    while (i < lines.length) {
      var m = RE_ITEM.exec(lines[i]) || RE_EMPTY_ITEM.exec(lines[i]);
      if (!m) {
        if (items.length && lines[i].trim() && /^\s{2,}/.test(lines[i])) {
          items[items.length - 1].lines.push(lines[i].replace(/^\s{2,}/, ""));
          i += 1;
          continue;
        }
        break;
      }
      var indent = m[1].length;
      if (indent < baseIndent) break;
      if (indent >= baseIndent + 2 && items.length) {
        items[items.length - 1].lines.push(lines[i].slice(baseIndent + 2));
        i += 1;
        continue;
      }
      if (/\d/.test(m[2]) !== ordered) break;
      items.push({ lines: [m[3] === undefined ? "" : m[3]] });
      i += 1;
    }

    function itemBody(lines) {
      var html = blocks(lines).join("");
      return html || "<p></p>";
    }

    if (ordered) {
      var n = parseInt(first[2], 10);
      var startAttr = n !== 1 && !isNaN(n) ? ' start="' + n + '"' : "";
      return {
        html: "<ol" + startAttr + ">" + items.map(function (it) {
          return "<li>" + itemBody(it.lines) + "</li>";
        }).join("") + "</ol>",
        next: i
      };
    }

    // Aufgaben und normale Punkte duerfen in Tiptap nicht in einer Liste
    // stehen -- also in aufeinanderfolgende Laeufe trennen.
    var runs = [];
    items.forEach(function (it) {
      var t = RE_TASK.exec(it.lines[0]);
      var task = !!t;
      if (t) it.lines[0] = t[2];
      it.checked = t && t[1].toLowerCase() === "x";
      if (!runs.length || runs[runs.length - 1].task !== task) runs.push({ task: task, items: [] });
      runs[runs.length - 1].items.push(it);
    });
    var html = runs.map(function (run) {
      if (run.task) {
        return '<ul data-type="taskList">' + run.items.map(function (it) {
          return '<li data-type="taskItem" data-checked="' + (it.checked ? "true" : "false") + '">' +
            itemBody(it.lines) + "</li>";
        }).join("") + "</ul>";
      }
      return "<ul>" + run.items.map(function (it) {
        return "<li>" + itemBody(it.lines) + "</li>";
      }).join("") + "</ul>";
    }).join("");
    return { html: html, next: i };
  }

  /* ---- Tabellen ---- */

  function splitRow(line) {
    var s = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    var cells = [];
    var cur = "";
    for (var i = 0; i < s.length; i++) {
      if (s[i] === "\\" && s[i + 1] === "|") { cur += "|"; i += 1; continue; }
      if (s[i] === "|") { cells.push(cur); cur = ""; continue; }
      cur += s[i];
    }
    cells.push(cur);
    return cells.map(function (c) { return c.trim(); });
  }

  function parseTable(lines, start) {
    var header = splitRow(lines[start]);
    var spec = splitRow(lines[start + 1]).map(function (c) {
      var l = c.charAt(0) === ":";
      var r = c.charAt(c.length - 1) === ":";
      return l && r ? "center" : r ? "right" : "left";
    });
    var cols = header.length;
    var rows = [];
    var i = start + 2;
    while (i < lines.length && lines[i].trim() && lines[i].indexOf("|") >= 0 && !startsBlock(lines, i)) {
      rows.push(splitRow(lines[i]));
      i += 1;
    }
    // Eine komplett leere Kopfzeile steht fuer "Tabelle ohne Kopf".
    var hasHeader = header.some(function (h) { return h.trim(); });

    function cell(tag, text, col) {
      return "<" + tag + ' data-align="' + (spec[col] || "left") + '"><p>' + inline(text) + "</p></" + tag + ">";
    }
    function row(cells, tag) {
      var h = "<tr>";
      for (var c = 0; c < cols; c++) h += cell(tag, cells[c] || "", c);
      return h + "</tr>";
    }
    var html = "<table>";
    if (hasHeader) html += row(header, "th");
    rows.forEach(function (r) { html += row(r, "td"); });
    html += "</table>";
    return { html: html, next: i };
  }

  global.MD = { toHtml: toHtml, inline: inline, esc: esc, escAttr: escAttr };
})(window);
