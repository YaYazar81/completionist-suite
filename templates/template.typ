// CompletionistPDF -- Layout-Template
//
// Alle Einstellungen kommen aus config.json, das die Engine neben diese Datei
// schreibt. Das Template selbst wird nie veraendert.
//
// Aufbau des Dokuments:
//   1. Deckblatt (randloses Vollbild oder gesetzte Titelseite)
//   2. Inhaltsverzeichnis  -> erstes PDF-Lesezeichen
//   3. Inhalt aus content.typ

#let cfg = json("config.json")

#let tp = cfg.typography
#let hf = cfg.header_footer
#let ct = cfg.content
#let toc = cfg.toc
#let wm = cfg.watermark
#let cv = cfg.cover

// Font-Fallback-Ketten: der Emoji-Font steht ueberall am Ende, damit Typst
// Emojis Glyphe fuer Glyphe daraus nachlaedt.
#let body-fonts = (tp.body_font, tp.emoji_font)
#let heading-fonts = (tp.heading_font, tp.body_font, tp.emoji_font)
#let mono-fonts = (tp.mono_font, tp.emoji_font)

#let page-margin = (
  top: cfg.margin_top * 1mm,
  bottom: cfg.margin_bottom * 1mm,
  left: (cfg.margin_left + cfg.binding_offset) * 1mm,
  right: cfg.margin_right * 1mm,
)

// ---------------------------------------------------------------------- //
// Wasserzeichen
// ---------------------------------------------------------------------- //

#let watermark = {
  if wm.mode == "text" and wm.text != "" {
    place(
      center + horizon,
      rotate(
        wm.angle * 1deg,
        text(
          size: wm.size * 1pt,
          weight: "bold",
          fill: rgb(wm.color).transparentize(100% - wm.opacity * 1%),
          wm.text,
        ),
      ),
    )
  } else if wm.mode == "image" and wm.image != "" {
    // Bilder kennen in Typst keine Deckkraft; deshalb liegt ein halb-
    // durchsichtiges weisses Rechteck darueber.
    place(
      center + horizon,
      rotate(
        wm.angle * 1deg,
        box(width: wm.size * 1%, {
          image(wm.image, width: 100%)
          place(
            top + left,
            rect(
              width: 100%,
              height: 100%,
              fill: white.transparentize(wm.opacity * 1%),
              stroke: none,
            ),
          )
        }),
      ),
    )
  }
}

// ---------------------------------------------------------------------- //
// Kopf- und Fusszeile
// ---------------------------------------------------------------------- //

#let starts-chapter() = {
  let p = here().page()
  query(heading.where(level: 1)).any(h => h.location().page() == p)
}

#let header-body = context {
  if hf.header_enabled and not (hf.skip_on_chapter_start and starts-chapter()) {
    let chapter = {
      // Die Verzeichnis-Ueberschrift zaehlt nicht als Kapitel -- sonst
      // stuende "Inhaltsverzeichnis" ueber dem Text vor dem ersten Kapitel.
      let hs = query(heading.where(level: 1).before(here()))
        .filter(h => not (h.has("label") and h.label == <toc-heading>))
      if hs.len() > 0 { hs.last().body } else { [] }
    }
    let shown = if hf.header_text == "{chapter}" {
      chapter
    } else if hf.header_text == "{title}" {
      cv.title
    } else {
      hf.header_text
    }
    set text(size: 0.85em, fill: luma(90))
    block(width: 100%, {
      shown
      if hf.header_rule {
        place(bottom, dy: 4pt, line(length: 100%, stroke: 0.4pt + luma(180)))
      }
    })
  }
}

#let page-label(current, total) = {
  hf.footer_format
    .replace("{page}", str(current))
    .replace("{total}", str(total))
}

#let footer-body = context {
  if hf.footer_enabled {
    let current = counter(page).at(here()).first()
    let total = counter(page).final().first()
    set text(size: 0.85em, fill: luma(90))
    block(width: 100%, {
      if hf.footer_rule {
        place(top, dy: -6pt, line(length: 100%, stroke: 0.4pt + luma(180)))
      }
      align(center, page-label(current, total))
    })
  }
}

// ---------------------------------------------------------------------- //
// Globale Stile
// ---------------------------------------------------------------------- //

#set document(
  title: if cv.title != "" { cv.title } else { "Dokument" },
  author: cv.author,
)

#set text(
  font: body-fonts,
  size: tp.body_size * 1pt,
  lang: tp.lang,
  hyphenate: tp.hyphenate,
)

#set par(
  justify: tp.justify,
  leading: tp.leading * 1em,
  spacing: tp.par_spacing * 1em,
  first-line-indent: tp.first_line_indent * 1em,
)

// Nummerierung nur bis zur eingestellten Tiefe (entspricht dem linken
// Schieberegler im LyX-Dialog). Tiefere Ebenen bekommen ausdruecklich
// `none` -- eine Funktion, die nur leeren Text liefert, wuerde Typst dazu
// bringen, ein Leerzeichen vor den Lesezeichen-Titel zu setzen.
#let num-for(level) = if level <= toc.numbering_depth { toc.numbering_pattern } else { none }
#show heading.where(level: 1): set heading(numbering: num-for(1))
#show heading.where(level: 2): set heading(numbering: num-for(2))
#show heading.where(level: 3): set heading(numbering: num-for(3))
#show heading.where(level: 4): set heading(numbering: num-for(4))
#show heading.where(level: 5): set heading(numbering: num-for(5))
#show heading.where(level: 6): set heading(numbering: num-for(6))

#show outline.entry.where(level: 1): set text(weight: "bold")
#show outline.entry.where(level: 1): set block(above: 0.9em)

// Aufnahme in Verzeichnis und PDF-Lesezeichen (rechter Schieberegler).
#show heading.where(level: 1): set heading(outlined: 1 <= toc.toc_depth)
#show heading.where(level: 2): set heading(outlined: 2 <= toc.toc_depth)
#show heading.where(level: 3): set heading(outlined: 3 <= toc.toc_depth)
#show heading.where(level: 4): set heading(outlined: 4 <= toc.toc_depth)
#show heading.where(level: 5): set heading(outlined: 5 <= toc.toc_depth)
#show heading.where(level: 6): set heading(outlined: 6 <= toc.toc_depth)

#show heading: set text(font: heading-fonts, weight: "bold")
#show heading: set block(above: 1.4em, below: 0.8em)
#show heading.where(level: 1): set text(size: 1.7em)
#show heading.where(level: 2): set text(size: 1.3em)
#show heading.where(level: 3): set text(size: 1.1em)

#show heading.where(level: 1): it => {
  // Die Verzeichnis-Ueberschrift sitzt schon auf einer eigenen Seite; ein
  // weiterer Umbruch wuerde dort eine Leerseite erzeugen.
  let is-toc = it.has("label") and it.label == <toc-heading>
  if ct.pagebreak_before_level1 and not is-toc { pagebreak(weak: true) }
  it
}

#show link: set text(fill: rgb(tp.link_color))

#show raw: set text(font: mono-fonts, size: ct.code_size * 1pt)
#show raw.where(block: true): it => block(
  width: 100%,
  fill: rgb(ct.code_background),
  inset: 8pt,
  radius: 3pt,
  stroke: if ct.code_border { 0.5pt + luma(215) } else { none },
  it,
)

#show figure: set block(breakable: false)
#show figure.caption: set text(size: 0.9em, fill: luma(80))

#show quote.where(block: true): it => block(
  width: 100%,
  inset: (left: 10pt, y: 6pt),
  stroke: (left: 2pt + luma(190)),
  text(style: "italic", it.body),
)

// ---------------------------------------------------------------------- //
// 1. Deckblatt
// ---------------------------------------------------------------------- //

#if cv.enabled {
  if cv.image != "" and cv.full_bleed {
    // Randlos: fit "cover" fuellt die Seite lueckenlos, ohne zu verzerren.
    page(
      paper: cfg.page_size,
      margin: 0pt,
      header: none,
      footer: none,
      background: none,
      numbering: none,
      image(cv.image, width: 100%, height: 100%, fit: "cover"),
    )
  } else {
    page(
      paper: cfg.page_size,
      margin: (x: 25mm, y: 35mm),
      header: none,
      footer: none,
      background: none,
      numbering: none,
      {
        if cv.image != "" {
          align(center, image(cv.image, width: 70%))
          v(1.5cm)
        }
        align(center + horizon, {
          text(size: 2.4em, weight: "bold", font: heading-fonts, cv.title)
          if cv.subtitle != "" {
            linebreak()
            v(0.4cm)
            text(size: 1.3em, fill: luma(70), cv.subtitle)
          }
          if cv.author != "" {
            v(2cm)
            text(size: 1.1em, cv.author)
          }
        })
      },
    )
  }
}

// ---------------------------------------------------------------------- //
// 2. Inhaltsverzeichnis -- traegt das erste PDF-Lesezeichen
// ---------------------------------------------------------------------- //

#if toc.enabled {
  if toc.roman_front_matter {
    counter(page).update(1)
  }
  page(
    paper: cfg.page_size,
    margin: page-margin,
    header: none,
    footer: context {
      set text(size: 0.85em, fill: luma(90))
      align(center, numbering("i", counter(page).at(here()).first()))
    },
    background: watermark,
    {
      [#heading(level: 1, numbering: none, outlined: true, bookmarked: true, toc.title) <toc-heading>]
      context outline(
        title: none,
        depth: toc.toc_depth,
        indent: 1.4em,
        target: heading.where(outlined: true).after(here()),
      )
    },
  )
}

// ---------------------------------------------------------------------- //
// 3. Inhalt
// ---------------------------------------------------------------------- //

#set page(
  paper: cfg.page_size,
  margin: page-margin,
  header: header-body,
  footer: footer-body,
  background: watermark,
)

#counter(page).update(1)

#include "content.typ"
