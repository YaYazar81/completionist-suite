// ProseMirror-Dokument -> Markdown im Dialekt von CompletionistPDF.
//
// Gegenstueck zu assets/editor/markdown.js: Was der Parser einliest, muss hier
// wieder als dieselbe Zeile herauskommen (Round-Trip).

export function serialize(doc) {
  const md = joinBlocks(doc).replace(/\n{3,}/g, "\n\n").trim();
  return md ? md + "\n" : "";
}

// Aufgaben- und Punktlisten sind in Tiptap getrennte Knoten, in Markdown aber
// eine einzige "-"-Liste. Eine Leerzeile dazwischen machte sie "loose".
const DASH_LISTS = new Set(["bulletList", "taskList"]);

function joinBlocks(parent) {
  let out = "";
  let prev = null;
  parent.forEach((node) => {
    const md = block(node);
    if (!md) return;
    if (out) out += prev && DASH_LISTS.has(prev) && DASH_LISTS.has(node.type.name) ? "\n" : "\n\n";
    out += md;
    prev = node.type.name;
  });
  return out;
}

function blocks(parent) {
  const md = joinBlocks(parent);
  return md ? [md] : [];
}

function block(node) {
  switch (node.type.name) {
    case "paragraph": {
      const text = inline(node).replace(/\s+$/, "");
      if (!text.trim()) return null;
      // Aufgeklappter Quelltext am Anfang ("## ", "- " vor dem Zuklappen, siehe
      // reveal.js) ist gemeinte Syntax -- die erste Zeile nicht maskieren.
      if (isSource(node.firstChild)) {
        const [first, ...rest] = text.split("\n");
        return rest.length ? first + "\n" + protectLineStarts(rest.join("\n")) : first;
      }
      return protectLineStarts(text);
    }
    case "heading":
      // Aufgeklappt (Cursor in der Ueberschrift) steht "## " schon als
      // Quelltext im Inhalt -- dann gilt genau das, was dort steht.
      if (isSource(node.firstChild) && node.textContent.startsWith("#")) return inline(node).trim();
      return "#".repeat(node.attrs.level) + " " + inline(node).trim();
    case "blockquote":
      return blocks(node)
        .join("\n\n")
        .split("\n")
        .map((l) => (l ? "> " + l : ">"))
        .join("\n");
    case "codeBlock": {
      const code = node.textContent;
      const longest = Math.max(2, ...(code.match(/`+/g) || []).map((s) => s.length));
      const fence = "`".repeat(longest + 1 > 3 ? longest + 1 : 3);
      return fence + (node.attrs.language || "") + "\n" + code + "\n" + fence;
    }
    case "rule":
      return node.attrs.kind === "break" ? "***" : "---";
    case "image":
      return imageMd(node.attrs);
    case "rawHtml":
      return node.attrs.raw || null;
    case "bulletList":
    case "orderedList":
    case "taskList":
      return list(node);
    case "table":
      return table(node);
    default:
      return node.isTextblock ? inline(node) : blocks(node).join("\n\n");
  }
}

// ------------------------------------------------------------------------
// Listen
// ------------------------------------------------------------------------

function list(node) {
  const ordered = node.type.name === "orderedList";
  let num = node.attrs.start || 1;
  const items = [];
  node.forEach((item) => {
    const task = item.type.name === "taskItem";
    const marker = task ? `- [${item.attrs.checked ? "x" : " "}] ` : ordered ? `${num++}. ` : "- ";
    // Inhalt rueckt bis zur Inhaltsspalte ein -- bei Aufgaben ist das die
    // Spalte nach "- ", das "[ ] " gehoert schon zum Text. Mehr Einzug
    // machte daraus einen eingerueckten Codeblock.
    const pad = " ".repeat(task ? 2 : marker.length);
    let text = "";
    item.forEach((child) => {
      const md = block(child);
      if (!md) return;
      // Unterlisten eng anschliessen, sonst wird die Liste "loose".
      if (text) text += /List$/.test(child.type.name) ? "\n" : "\n\n";
      text += md;
    });
    const lines = text.split("\n");
    const first = lines.shift() || "";
    const rest = lines.map((l) => (l ? pad + l : ""));
    items.push(marker + first + (rest.length ? "\n" + rest.join("\n") : ""));
  });
  return items.join("\n");
}

// ------------------------------------------------------------------------
// Tabellen
// ------------------------------------------------------------------------

function table(node) {
  const rows = [];
  node.forEach((row) => rows.push(row));
  if (!rows.length) return null;
  const cols = Math.max(...rows.map((r) => r.childCount));

  const cellText = (cell) => {
    const parts = [];
    cell.forEach((child) => {
      const t = child.isTextblock ? inline(child) : block(child);
      if (t && t.trim()) parts.push(t.trim());
    });
    return parts.join(" ").replace(/\n/g, " ").replace(/\|/g, "\\|");
  };
  const cells = (row) => {
    const out = [];
    row.forEach((c) => out.push(cellText(c)));
    while (out.length < cols) out.push("");
    return out;
  };
  const line = (arr) => "| " + arr.join(" | ") + " |";

  const first = rows[0];
  let headerIsReal = first.childCount > 0;
  first.forEach((c) => {
    if (c.type.name !== "tableHeader") headerIsReal = false;
  });

  const aligns = [];
  first.forEach((c) => aligns.push(c.attrs.align || "left"));
  while (aligns.length < cols) aligns.push("left");
  const sep = aligns.map((a) => (a === "center" ? ":---:" : a === "right" ? "---:" : ":---"));

  // Markdown verlangt eine Kopfzeile -- ohne echte bleibt sie leer.
  const header = headerIsReal ? cells(first) : new Array(cols).fill("");
  const body = (headerIsReal ? rows.slice(1) : rows).map((r) => line(cells(r)));
  return [line(header), line(sep)].concat(body).join("\n");
}

// ------------------------------------------------------------------------
// Bilder
// ------------------------------------------------------------------------

function encodeSrc(src) {
  return /[\s()]/.test(src) ? "<" + src + ">" : src;
}

function escAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

export function imageMd(attrs) {
  const src = attrs.src || "";
  const alt = attrs.alt || "";
  const align = attrs.align || "center";
  const width = attrs.width || "";
  if (align === "center" && !width) {
    // Reines Markdown, solange nichts Zusaetzliches noetig ist.
    return "![" + alt.replace(/([\[\]])/g, "\\$1") + "](" + encodeSrc(src) + ")";
  }
  // CompletionistPDF liest dieses Tag (md_converter._html_image).
  let out = `<img src="${escAttr(src)}" align="${escAttr(align)}"`;
  if (width) out += ` width="${escAttr(width)}"`;
  if (alt) out += ` alt="${escAttr(alt)}"`;
  return out + ">";
}

// ------------------------------------------------------------------------
// Inline-Ebene mit sauber verschachtelten Markierungen
// ------------------------------------------------------------------------

const MARK_ORDER = ["link", "bold", "italic", "strike", "underline", "code"];

function sortMarks(marks) {
  return marks
    .filter((m) => MARK_ORDER.includes(m.type.name))
    .slice()
    .sort((a, b) => MARK_ORDER.indexOf(a.type.name) - MARK_ORDER.indexOf(b.type.name));
}

function openMark(mark, text) {
  switch (mark.type.name) {
    case "bold": return "**";
    case "italic": return "*";
    case "strike": return "~~";
    case "underline": return "<u>";
    case "code": return text.includes("`") ? "`` " : "`";
    case "link": return "[";
    default: return "";
  }
}

function closeMark(mark, ticks) {
  switch (mark.type.name) {
    case "bold": return "**";
    case "italic": return "*";
    case "strike": return "~~";
    case "underline": return "</u>";
    case "code": return ticks === "`` " ? " ``" : "`";
    case "link": {
      const href = mark.attrs.href || "";
      const title = mark.attrs.title;
      return "](" + encodeSrc(href) + (title ? ` "${title}"` : "") + ")";
    }
    default: return "";
  }
}

/** Aufgeklappter Markdown-Quelltext (reveal.js) -- wird unveraendert geschrieben. */
function isSource(node) {
  return !!node && node.isText && node.marks.some((m) => m.type.name === "mdSource");
}

export { inline as inlineMarkdown };

function inline(parent) {
  let out = "";
  let open = []; // [{ mark, opener }]

  const closeFrom = (keep) => {
    if (open.length <= keep) return;
    // Leerraum am Ende gehoert vor die schliessende Markierung hinaus:
    // "**fett **" ist kein Fettdruck.
    const ws = /\s*$/.exec(out)[0];
    out = out.slice(0, out.length - ws.length);
    for (let i = open.length - 1; i >= keep; i--) out += closeMark(open[i].mark, open[i].opener);
    out += ws;
    open = open.slice(0, keep);
  };

  parent.forEach((node) => {
    let text;
    if (node.isText) {
      const inCode = node.marks.some((m) => m.type.name === "code");
      text = inCode || isSource(node) ? node.text : escapeText(node.text);
    } else if (node.type.name === "hardBreak") {
      text = node.attrs.soft ? "\n" : "  \n";
    } else if (node.type.name === "inlineImage") {
      text = "![" + (node.attrs.alt || "") + "](" + encodeSrc(node.attrs.src || "") + ")";
    } else {
      text = node.textContent || "";
    }

    // Reiner Leerraum braucht keine Formatierung (vermeidet "** **").
    const marks = node.isText && !text.trim() ? [] : sortMarks(node.marks);

    let keep = 0;
    while (keep < open.length && keep < marks.length && open[keep].mark.eq(marks[keep])) keep++;
    // Nur schliessen, wenn die Markierung wirklich endet -- Leerraum ohne
    // Markierung mitten im fetten Text laesst sie offen.
    if (!(node.isText && !text.trim() && marks.length === 0)) closeFrom(keep);

    if (marks.length > keep) {
      const lead = /^\s*/.exec(text)[0];
      out += lead;
      text = text.slice(lead.length);
      for (let i = keep; i < marks.length; i++) {
        const opener = openMark(marks[i], text);
        out += opener;
        open.push({ mark: marks[i], opener });
      }
    }
    out += text;
  });
  closeFrom(0);
  return out;
}

function isWordChar(c) {
  return !!c && /[\wÀ-ɏ]/.test(c);
}

/** Text so maskieren, dass Markdown ihn wieder als Text liest -- nur dort,
 *  wo Verwechslungsgefahr besteht (snake_case bleibt snake_case). */
function escapeText(text) {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "\\" || c === "`" || c === "*" || c === "[") out += "\\" + c;
    else if (c === "_") out += isWordChar(text[i - 1]) && isWordChar(text[i + 1]) ? "_" : "\\_";
    else if (c === "~" && (text[i + 1] === "~" || text[i - 1] === "~")) out += "\\~";
    // Nur ein "<", das ein Tag oder Autolink beginnen koennte; "a < b" bleibt.
    else if (c === "<" && /[A-Za-z\/!?]/.test(text[i + 1] || "")) out += "&lt;";
    else if (c === "&" && /^&(#\d+|#x[0-9a-f]+|[a-z][a-z0-9]*);/i.test(text.slice(i))) out += "&amp;";
    else if (c === " ") out += " ";
    else out += c;
  }
  return out;
}

function protectLineStarts(body) {
  // Zeilen, die sonst als Liste/Ueberschrift/Zitat gelesen wuerden.
  return body
    .split("\n")
    .map((l) => l.replace(/^(\s*)([#>]|\d+\.(?=\s)|[-*+](?=\s))/, "$1\\$2"))
    .join("\n");
}
