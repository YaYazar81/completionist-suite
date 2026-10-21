// Hilfsfunktionen, die der Konverter in content.typ aufruft.
//
// Eigene Datei, weil `include` in Typst einen eigenen Modul-Scope erzeugt:
// content.typ sieht die Definitionen aus main.typ nicht und importiert
// deshalb diese Datei.

#let cfg = json("config.json")
#let ct = cfg.content

/// Ankreuzkaestchen fuer Aufgabenlisten ("- [ ]" / "- [x]").
///
/// Rahmen und Haken sind gezeichnet statt als Schriftzeichen gesetzt: So sehen
/// sie in jeder Schrift gleich aus, und kein Emoji-Font springt ein.
#let md-checkbox(done) = box(
  width: 0.8em,
  height: 0.8em,
  baseline: 0.1em,
  stroke: 0.7pt + luma(70),
  radius: 1.5pt,
  if done {
    place(curve(
      stroke: (paint: luma(30), thickness: 1.1pt, cap: "round", join: "round"),
      curve.move((0.17em, 0.42em)),
      curve.line((0.34em, 0.6em)),
      curve.line((0.64em, 0.2em)),
    ))
  },
)

/// Ein Listenpunkt: `done` ist true, false oder none (normaler Punkt).
#let md-task(done, body) = (done: done, body: body)

/// Aufgabenliste mit haengendem Einzug: umbrechender Text beginnt unter dem
/// Text, nicht unter dem Kaestchen.
#let md-tasklist(..items) = {
  let rows = items.pos().map(it => grid(
    columns: (1.15em, 1fr),
    column-gutter: 0.3em,
    if it.done == none { align(center, sym.bullet) } else { md-checkbox(it.done) },
    it.body,
  ))
  list(marker: [], indent: 0pt, body-indent: 0pt, ..rows)
}

/// Vom Text umflossenes Bild (`<img align="left|right">` aus CompletionistMD).
///
/// Bewusst eine *Naeherung*, kein zeilengenauer Umfluss: Typst kann Text
/// nicht ueber Bereiche unterschiedlicher Breite fliessen lassen, und echtes
/// Umbrechen hiesse, Absaetze wortweise zu zerlegen -- fragil bei Fettdruck,
/// Links, Fussnoten. Stattdessen wird *absatzweise* verteilt:
///
/// - Das Bild steht oben am linken bzw. rechten Rand, daneben eine
///   Textspalte (zweispaltiges Grid). Diese Spalte wird mit ganzen Bloecken
///   aus `body` gefuellt, bis sie etwa so hoch ist wie das Bild. Fuer den
///   Block, der ueber die Bildunterkante ragt, entscheidet die geringere
///   Leerflaeche, ob er noch neben das Bild kommt -- der erste Block steht
///   immer daneben.
/// - Alle uebrigen Bloecke laufen darunter in voller Breite weiter.
///
/// Ein sehr langer Absatz direkt nach dem Bild laeuft deshalb komplett in
/// der schmalen Spalte und laesst unter dem Bild Platz frei.
///
/// - side: "left" oder "right"
/// - width: Bildbreite (Ratio wie 40%, Laenge oder auto = Eigenbreite des Bilds)
/// - img: das Bild, mit `width: 100%` (oder fester Hoehe, wenn width auto ist);
///   darf eine `figure` mit Bildunterschrift sein
/// - body: Array der Textbloecke (auch leer); einzelner Inhalt geht auch
#let md-wrap(side, width, img, body) = layout(size => {
  let blocks = if type(body) == array { body } else { (body,) }
  let gap = 1.2em.to-absolute()

  let img-w = if width == auto {
    measure(img).width
  } else if type(width) == ratio {
    width * size.width
  } else if type(width) == length {
    width.to-absolute()
  } else {
    width.ratio * size.width + width.length.to-absolute()
  }
  img-w = calc.min(img-w, size.width)
  let pic = box(width: img-w, img)
  let img-h = measure(pic).height
  let text-w = size.width - img-w - gap

  // Kein Text oder kein Platz daneben: Bild allein am Rand, Text darunter.
  if blocks.len() == 0 or text-w < 8em.to-absolute() {
    block(width: 100%, align(if side == "right" { right } else { left }, pic))
    blocks.join(parbreak())
    return
  }

  let side-h(k) = if k == 0 { 0pt } else {
    measure(block(width: text-w, blocks.slice(0, k).join(parbreak()))).height
  }
  let k = 1
  while k < blocks.len() and side-h(k) < img-h { k += 1 }
  if k > 1 and side-h(k) > img-h {
    // Ueberstehender Block: dorthin, wo weniger Leerflaeche entsteht.
    if img-h - side-h(k - 1) < side-h(k) - img-h { k -= 1 }
  }

  let column = blocks.slice(0, k).join(parbreak())
  block(breakable: false, grid(
    columns: if side == "right" { (1fr, img-w) } else { (img-w, 1fr) },
    column-gutter: gap,
    ..if side == "right" { (column, pic) } else { (pic, column) },
  ))
  blocks.slice(k).join(parbreak())
})

/// Tabelle im eingestellten Stil.
///
/// - columns: Spaltenzahl
/// - aligns: Ausrichtung je Spalte als Typst-Werte (left/center/right)
/// - has-header: ob die ersten `columns` Zellen die Kopfzeile bilden
#let md-table(columns: 1, aligns: (), has-header: true, ..cells) = {
  let c = cells.pos()
  let style = ct.table_style
  let rule = 0.5pt + luma(170)

  let stroke-spec = if style == "grid" {
    rule
  } else if style == "header" and has-header {
    (x, y) => (top: if y == 1 { rule } else { none })
  } else {
    none
  }

  let fill-fn = (x, y) => {
    if has-header and y == 0 and style != "none" {
      luma(238)
    } else if ct.table_zebra and calc.odd(y) {
      luma(248)
    } else {
      none
    }
  }

  let head = if has-header { c.slice(0, columns) } else { () }
  let body-cells = if has-header { c.slice(columns) } else { c }
  if ct.table_header_bold {
    head = head.map(h => strong(h))
  }

  table(
    columns: columns,
    align: (x, y) => aligns.at(x, default: left),
    stroke: stroke-spec,
    fill: fill-fn,
    inset: (x: 7pt, y: 6pt),
    ..if has-header { (table.header(..head),) } else { () },
    ..body-cells,
  )
}
