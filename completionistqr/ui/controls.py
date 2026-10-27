"""Linke Bedienleiste mit den Reitern Inhalt, Design, Logo, Beschriftung und Export."""
from __future__ import annotations

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..core import export, fonts, payload, presets
from ..core.config import ECC_LEVELS, QRDesign
from ..core.render_pil import render
from . import style
from .drive_upload import DriveUploadPanel
from .widgets import Choice, ColorPicker, ValueSlider, row, section

MODULE_LABELS = {"square": "Quadrate", "gapped_square": "Quadrate mit Abstand",
                 "circle": "Punkte", "rounded": "Abgerundet (fließend)", "diamond": "Rauten",
                 "vertical_bars": "Vertikale Balken", "horizontal_bars": "Horizontale Balken"}
EYE_LABELS = {"square": "Eckig", "rounded": "Abgerundet", "circle": "Kreis",
              "leaf": "Blatt", "drop": "Tropfen", "dots": "Punkte"}
GRADIENT_LABELS = {"none": "Kein Verlauf", "linear": "Linear", "radial": "Radial"}
FRAME_LABELS = {"none": "Ohne Rahmen", "thin": "Feine Linie", "card": "Karte",
                "banner_bottom": "Banner unten", "banner_top": "Banner oben", "ticket": "Ticket",
                "arrow": "Handschrift mit Pfeil"}
POSITION_LABELS = {"bottom": "Unter dem Code", "top": "Über dem Code"}
CONTENT_LABELS = {"url": "Website", "vcard": "Kontakt (vCard)", "wifi": "WLAN-Zugang",
                  "email": "E-Mail", "sms": "SMS", "whatsapp": "WhatsApp", "phone": "Telefon",
                  "payment": "Zahlung (GiroCode / PayPal)", "geo": "Standort",
                  "social": "Social Media", "app": "App-Link", "feedback": "Feedback",
                  "file": "PDF, Bild oder Video (Link)", "text": "Freitext"}
SECURITY_LABELS = {"WPA": "WPA / WPA2 / WPA3", "WEP": "WEP", "nopass": "Offen (ohne Passwort)"}
PAYMENT_LABELS = {"epc": "SEPA-Überweisung (GiroCode)", "paypal": "PayPal.me"}
GEO_LABELS = {"maps": "Kartenlink (jedes Handy)", "geo": "geo:-Koordinaten (nur Android)"}
SOCIAL_LABELS = {k: v[0] for k, v in payload.SOCIAL.items()}
APP_LABELS = {"android": "Google Play (Android)", "ios": "App Store (iPhone)", "other": "Anderer Link"}
# Auswahlfelder: Art "choice:<Name>" -> Beschriftungen
CHOICES = {"security": SECURITY_LABELS, "payment": PAYMENT_LABELS, "geo": GEO_LABELS,
           "social": SOCIAL_LABELS, "app": APP_LABELS}

# Hinweise unter dem Formular
HINTS = {
    "payment": "GiroCode lesen die Banking-Apps deutscher Banken und Sparkassen: Empfänger, IBAN, "
               "Betrag und Verwendungszweck sind dann schon ausgefüllt. Betrag leer = frei wählbar.",
    "geo": "Mit Adresse wird nach ihr gesucht, sonst nach den Koordinaten. Der Kartenlink "
           "öffnet auf iPhone und Android, geo: nur auf Android.",
    "app": "Ein Code für beide Stores bräuchte eine Weiterleitungsseite im Netz – hier "
           "zeigt der Code auf genau einen Store.",
    "file": "Der Code enthält nur einen Link. Mit dem Knopf unten wird die Datei in Google "
            "Drive hochgeladen und für „Jeder mit dem Link“ freigegeben. Oder einen "
            "vorhandenen Freigabe-Link (Dropbox, YouTube …) einfügen.",
    "whatsapp": "Nummer mit Ländervorwahl; 0170 … wird als deutsche Nummer (+49) gelesen.",
    "feedback": "Link zu einem Formular (z. B. Google Forms). Ohne Link öffnet der Code eine "
                "E-Mail an die Adresse.",
}

# (Schlüssel, Beschriftung, Art) – Art: entry | multi | switch | choice:<Name>
FIELDS = {
    "url": [("url", "Adresse", "entry")],
    "text": [("text", "Text", "multi")],
    "wifi": [("ssid", "Netzwerkname", "entry"), ("password", "Passwort", "entry"),
             ("security", "Verschlüsselung", "choice:security"),
             ("hidden", "Verstecktes Netz", "switch")],
    "payment": [("kind", "Art", "choice:payment"), ("name", "Empfänger", "entry"),
                ("iban", "IBAN", "entry"), ("bic", "BIC (optional)", "entry"),
                ("paypal", "PayPal.me-Name", "entry"), ("amount", "Betrag in €", "entry"),
                ("purpose", "Verwendungszweck", "entry")],
    "whatsapp": [("number", "Handynummer", "entry"), ("message", "Vorgabetext", "multi")],
    "social": [("platform", "Netzwerk", "choice:social"), ("handle", "Benutzername", "entry")],
    "app": [("store", "Store", "choice:app"), ("link", "Link zur App", "entry")],
    "feedback": [("link", "Formular-Link", "entry"), ("address", "oder E-Mail an", "entry"),
                 ("subject", "Betreff", "entry")],
    "file": [("link", "Freigabe-Link", "entry")],
    "vcard": [("first", "Vorname", "entry"), ("last", "Nachname", "entry"),
              ("org", "Firma", "entry"), ("title", "Position", "entry"),
              ("phone", "Telefon", "entry"), ("email", "E-Mail", "entry"),
              ("street", "Straße", "entry"), ("zip_code", "PLZ", "entry"),
              ("city", "Ort", "entry"), ("country", "Land", "entry"),
              ("website", "Website", "entry")],
    "email": [("address", "Empfänger", "entry"), ("subject", "Betreff", "entry"),
              ("body", "Nachricht", "multi")],
    "phone": [("number", "Nummer", "entry")],
    "sms": [("number", "Nummer", "entry"), ("message", "Nachricht", "multi")],
    "geo": [("mode", "Art", "choice:geo"), ("address", "Adresse", "entry"),
            ("lat", "Breitengrad", "entry"), ("lon", "Längengrad", "entry")],
}
# Felder, die nur bei einer bestimmten Auswahl sichtbar sind: (Typ, Feld) -> (Auswahlfeld, Werte)
ONLY_WHEN = {
    ("payment", "name"): ("kind", {"epc"}), ("payment", "iban"): ("kind", {"epc"}),
    ("payment", "bic"): ("kind", {"epc"}), ("payment", "purpose"): ("kind", {"epc"}),
    ("payment", "paypal"): ("kind", {"paypal"}),
    ("geo", "address"): ("mode", {"maps"}),
}
DEFAULTS = {("url", "url"): "https://example.com", ("wifi", "security"): "WPA",
            ("payment", "kind"): "epc", ("geo", "mode"): "maps", ("social", "platform"): "instagram",
            ("app", "store"): "android", ("feedback", "subject"): "Feedback"}

LOGO_TYPES = [("Bilder", "*.png *.jpg *.jpeg *.webp *.avif *.bmp *.gif"), ("Alle Dateien", "*.*")]
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".bmp", ".gif"}


class Controls(ctk.CTkTabview):
    """``fixed_payload``: der Inhalt steht fest (CompletionistQR Online: der Kurzlink) -- der Reiter
    Inhalt zeigt ihn nur an, statt Inhaltstyp und Formular; den Stapel-Export gibt es dann
    nicht. ``app`` ist das Fenster mit ``design``, ``changed()``, ``apply_preset()`` und
    ``preview`` (siehe designer.py)."""

    def __init__(self, master, app, fixed_payload: str | None = None, fixed_hint: str = ""):
        super().__init__(master, width=480, corner_radius=6, border_width=1,
                         border_color=style.BORDER)
        self.app = app
        self.fixed_payload = fixed_payload
        self.fixed_hint = fixed_hint
        self._refreshers: list = []
        self._values: dict[str, dict[str, ctk.Variable]] = {}
        self.content_type = "url"

        tabs = {}
        for name in ("Inhalt", "Design", "Logo", "Beschriftung", "Export"):
            self.add(name)
            # Explizites Hell/Dunkel-Farbpaar statt "transparent": sonst friert CTkScrollableFrame
            # die beim Start gültige Farbe ein und der Inhalt bleibt nach dem Umschalten dunkel.
            tabs[name] = ctk.CTkScrollableFrame(self.tab(name), fg_color=self.cget("fg_color"))
            tabs[name].pack(fill="both", expand=True)
        self._build_content(tabs["Inhalt"])
        self._build_design(tabs["Design"])
        self._build_logo(tabs["Logo"])
        self._build_caption(tabs["Beschriftung"])
        self._build_export(tabs["Export"])

    # ================================================================ Hilfen

    @property
    def d(self) -> QRDesign:
        return self.app.design

    def _set(self, field: str, value) -> None:
        setattr(self.d, field, value)
        self.app.changed()

    def _on_refresh(self, refresher) -> None:
        self._refreshers.append(refresher)

    def refresh(self) -> None:
        """Setzt alle Bedienelemente auf die Werte des aktuellen Designs."""
        for r in self._refreshers:
            r()

    def _choice(self, parent, label, field, labels):
        w = Choice(row(parent, label), labels, getattr(self.d, field),
                   lambda k: self._set(field, k), width=220)
        w.grid(row=0, column=1, sticky="ew")
        self._on_refresh(lambda: w.set_key(getattr(self.d, field)))
        return w

    def _color(self, parent, label, field):
        w = ColorPicker(row(parent, label), getattr(self.d, field), lambda c: self._set(field, c))
        w.grid(row=0, column=1, sticky="w")
        self._on_refresh(lambda: w.set(getattr(self.d, field)))
        return w

    def _switch(self, parent, label, field):
        var = ctk.BooleanVar(value=getattr(self.d, field))
        w = ctk.CTkSwitch(row(parent, label), text="", variable=var,
                          command=lambda: self._set(field, var.get()))
        w.grid(row=0, column=1, sticky="w")
        self._on_refresh(lambda: var.set(getattr(self.d, field)))
        return w

    def _slider(self, parent, label, field, from_, to, steps=None, scale=1.0,
                fmt=lambda v: f"{v:.0f}", as_int=False):
        def moved(v):
            v = v / scale
            self._set(field, int(round(v)) if as_int else v)
        w = ValueSlider(row(parent, label), from_, to, getattr(self.d, field) * scale, moved,
                        steps=steps, fmt=fmt)
        w.grid(row=0, column=1, sticky="ew")
        self._on_refresh(lambda: w.set(getattr(self.d, field) * scale))
        return w

    # ================================================================ Inhalt

    def _build_content(self, tab) -> None:
        if self.fixed_payload is not None:
            self._build_fixed_content(tab)
        else:
            self._build_content_form(tab)

        section(tab, "Fehlerkorrektur")
        ctk.CTkLabel(tab, text="H verträgt die meisten Störungen und ist für Logos nötig.",
                     text_color=style.MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=4)
        ecc = ctk.CTkSegmentedButton(tab, values=ECC_LEVELS, command=lambda v: self._set("ecc", v))
        ecc.set(self.d.ecc)
        ecc.pack(anchor="w", padx=4, pady=6)
        self._on_refresh(lambda: ecc.set(self.d.ecc))

        self.payload_error = ctk.CTkLabel(tab, text="", text_color=style.DANGER,
                                          anchor="w", wraplength=380)
        self.payload_error.pack(fill="x", padx=4, pady=6)

    def _build_fixed_content(self, tab) -> None:
        section(tab, "Im QR-Code")
        self.fixed_var = ctk.StringVar(value=self.fixed_payload)
        ctk.CTkEntry(tab, textvariable=self.fixed_var, state="readonly").pack(fill="x", padx=4, pady=4)
        if self.fixed_hint:
            ctk.CTkLabel(tab, text=self.fixed_hint, text_color=("gray35", "gray65"), anchor="w",
                         justify="left", wraplength=380).pack(fill="x", padx=4)

    def set_fixed_payload(self, text: str) -> None:
        self.fixed_payload = text
        self.fixed_var.set(text)
        self._update_payload()

    def _build_content_form(self, tab) -> None:
        section(tab, "Was soll der QR-Code enthalten?")
        self.content_choice = Choice(row(tab, "Inhaltstyp"), CONTENT_LABELS, self.content_type,
                                     self._content_type_changed, width=220)
        self.content_choice.grid(row=0, column=1, sticky="ew")
        self.form = ctk.CTkFrame(tab, fg_color="transparent")
        self.form.pack(fill="x")
        # Gehoert nicht ins Formular: das wird beim Wechsel neu gebaut, ein laufender
        # Upload soll das ueberleben.
        self.drive_upload = DriveUploadPanel(
            tab, on_link=lambda link: self._var("file", "link", "entry").set(link))
        self._build_form()

    def _var(self, ctype: str, key: str, kind: str) -> ctk.Variable:
        store = self._values.setdefault(ctype, {})
        if key not in store:
            if kind == "switch":
                store[key] = ctk.BooleanVar(value=False)
            else:
                store[key] = ctk.StringVar(value=DEFAULTS.get((ctype, key), ""))
            store[key].trace_add("write", lambda *_: self._update_payload())
        return store[key]

    def _build_form(self) -> None:
        for child in self.form.winfo_children():
            child.destroy()
        t = self.content_type
        for key, label, kind in FIELDS[t]:
            var = self._var(t, key, kind)
            cond = ONLY_WHEN.get((t, key))
            if cond and self._var(t, cond[0], "choice").get() not in cond[1]:
                continue
            r = row(self.form, label)
            if kind == "entry":
                ctk.CTkEntry(r, textvariable=var).grid(row=0, column=1, sticky="ew")
            elif kind == "multi":
                box = ctk.CTkTextbox(r, height=80, wrap="word")
                box.insert("1.0", var.get())
                box.bind("<KeyRelease>", lambda _e, b=box, v=var: v.set(b.get("1.0", "end-1c")))
                box.grid(row=0, column=1, sticky="ew")
            elif kind.startswith("choice:"):
                # Haengen andere Felder an dieser Auswahl, das Formular neu aufbauen
                rebuild = any(c[0] == key for (ct, _f), c in ONLY_WHEN.items() if ct == t)

                def chosen(value, v=var, rb=rebuild):
                    v.set(value)
                    if rb:
                        self.after_idle(self._build_form)
                Choice(r, CHOICES[kind.split(":", 1)[1]], var.get(), chosen, width=220).grid(
                    row=0, column=1, sticky="ew")
            elif kind == "switch":
                ctk.CTkSwitch(r, text="", variable=var).grid(row=0, column=1, sticky="w")
        if t in HINTS:
            ctk.CTkLabel(self.form, text=HINTS[t], text_color=style.MUTED, anchor="w",
                         justify="left", wraplength=380).pack(fill="x", padx=4, pady=(6, 0))
        if t == "file":
            self.drive_upload.pack(fill="x", after=self.form)
        else:
            self.drive_upload.pack_forget()

    def _content_type_changed(self, ctype: str) -> None:
        self.content_type = ctype
        self._build_form()
        self._update_payload()

    def _update_payload(self) -> None:
        if self.fixed_payload is not None:
            self._set("payload", self.fixed_payload)
            return
        t = self.content_type
        v = {k: var.get() for k, var in self._values.get(t, {}).items()}
        g = lambda k: v.get(k, DEFAULTS.get((t, k), ""))  # noqa: E731
        try:
            if t == "url":
                text = payload.url(g("url"))
            elif t == "text":
                text = payload.text(g("text"))
            elif t == "wifi":
                text = payload.wifi(g("ssid"), g("password"), g("security"), bool(v.get("hidden")))
            elif t == "vcard":
                text = payload.vcard(**{k: g(k) for k, _, _ in FIELDS["vcard"]})
            elif t == "email":
                text = payload.email(g("address"), g("subject"), g("body"))
            elif t == "phone":
                text = payload.phone(g("number"))
            elif t == "sms":
                text = payload.sms(g("number"), g("message"))
            elif t == "whatsapp":
                text = payload.whatsapp(g("number"), g("message"))
            elif t == "payment":
                if g("kind") == "paypal":
                    text = payload.paypal(g("paypal"), g("amount"))
                else:
                    text = payload.epc(g("name"), g("iban"), g("amount"), g("purpose"), g("bic"))
            elif t == "social":
                text = payload.social(g("platform"), g("handle"))
            elif t in ("app", "file"):
                if not g("link").strip():
                    raise ValueError("Bitte den Link eingeben.")
                text = payload.url(g("link"))
            elif t == "feedback":
                text = payload.feedback(g("link"), g("address"), g("subject"))
            elif g("mode") == "maps" and g("address").strip():
                text = payload.maps(address=g("address"))
            else:
                if not g("lat") or not g("lon"):
                    raise ValueError("Bitte Adresse oder Breiten- und Längengrad eingeben."
                                     if g("mode") == "maps" else "Bitte Breiten- und Längengrad eingeben.")
                text = (payload.maps(g("lat"), g("lon")) if g("mode") == "maps"
                        else payload.geo(g("lat"), g("lon")))
        except ValueError as exc:
            msg = str(exc) if str(exc).startswith(("Bitte", "Die", "Der")) \
                else "Bitte als Zahl eingeben, z. B. 52.5200 bzw. 12,50"
            self.payload_error.configure(text=msg)
            return
        self.payload_error.configure(text="")
        self._set("payload", text)

    # ================================================================ Design

    def _build_design(self, tab) -> None:
        section(tab, "Vorlagen")
        self.gallery = ctk.CTkFrame(tab, fg_color="transparent")
        self.gallery.pack(fill="x", padx=2)
        self._build_gallery()
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=(6, 0))
        ctk.CTkButton(bar, text="Aktuelles Design speichern …", image=style.icon("save"),
                      command=self._save_preset).pack(side="left")
        self.delete_btn = ctk.CTkButton(bar, text="Eigene Vorlage löschen …", width=10,
                                        image=style.icon("trash-2"), **style.secondary(),
                                        command=self._delete_preset)
        self.delete_btn.pack(side="left", padx=8)

        section(tab, "Module")
        self._choice(tab, "Form", "module_style", MODULE_LABELS)
        self._color(tab, "Farbe", "fg_color")
        self._choice(tab, "Farbverlauf", "gradient", GRADIENT_LABELS)
        self._color(tab, "Verlaufsfarbe", "gradient_color")
        self._slider(tab, "Winkel", "gradient_angle", 0, 360, steps=72, as_int=True,
                     fmt=lambda v: f"{v:.0f}°")

        section(tab, "Hintergrund")
        self._color(tab, "Farbe", "bg_color")
        self._switch(tab, "Transparent", "transparent_bg")
        self._slider(tab, "Ruhezone", "border", 1, 8, steps=7, as_int=True,
                     fmt=lambda v: f"{v:.0f} Mod.")

        section(tab, "Ecken-Marker (Augen)")
        self._choice(tab, "Rahmen", "eye_outer_style", EYE_LABELS)
        self._choice(tab, "Pupille", "eye_inner_style", EYE_LABELS)
        self._switch(tab, "Eigene Farben", "eye_custom_color")
        self._color(tab, "Rahmenfarbe", "eye_outer_color")
        self._color(tab, "Pupillenfarbe", "eye_inner_color")

    def _build_gallery(self) -> None:
        for child in self.gallery.winfo_children():
            child.destroy()
        self._thumbs = []
        user = presets.user()
        scale = self._get_widget_scaling()  # scharf auch bei 125/150 % Windows-Skalierung
        for i, (name, preset) in enumerate(presets.all_presets().items()):
            d = QRDesign(payload="CompletionistQR").apply_style(preset)
            d.caption = preset.get("caption", "Scan mich!" if d.frame == "arrow" else
                                  "SCAN ME" if d.frame.startswith("banner") or
                                  d.frame == "ticket" else "")
            img = render(d, round(76 * scale), supersample=2)
            thumb = ctk.CTkImage(light_image=img, dark_image=img,
                                 size=(round(img.width / scale), round(img.height / scale)))
            self._thumbs.append(thumb)
            label = name + (" ★" if name in user else "")
            ctk.CTkButton(self.gallery, image=thumb, text=label, compound="top", width=96,
                          height=110, fg_color=style.INPUT, border_color=style.BORDER,
                          hover_color=style.HOVER, text_color=style.TEXT,
                          font=ctk.CTkFont(size=11),
                          command=lambda s=preset: self.app.apply_preset(s)).grid(
                row=i // 4, column=i % 4, padx=3, pady=3)
        self.after_idle(lambda: self.delete_btn.configure(
            state="normal" if user else "disabled") if hasattr(self, "delete_btn") else None)

    def _save_preset(self) -> None:
        name = ctk.CTkInputDialog(title="Vorlage speichern", text="Name der Vorlage:").get_input()
        if name and name.strip():
            presets.save_user(name.strip(), self.d)
            self._build_gallery()

    def _delete_preset(self) -> None:
        user = list(presets.user())
        if not user:
            return
        name = ctk.CTkInputDialog(
            title="Vorlage löschen",
            text="Welche eigene Vorlage löschen?\n" + "\n".join(f"• {n}" for n in user)).get_input()
        if name and name.strip() in user:
            presets.delete_user(name.strip())
            self._build_gallery()

    # ================================================================ Logo

    def _build_logo(self, tab) -> None:
        section(tab, "Logo in der Mitte")
        bar = ctk.CTkFrame(tab, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=4)
        ctk.CTkButton(bar, text="Logo wählen …", image=style.icon("image"),
                      command=self._pick_logo).pack(side="left")
        ctk.CTkButton(bar, text="Einfügen", width=90, image=style.icon("clipboard-paste"),
                      **style.secondary(),
                      command=self._paste_logo_clicked).pack(side="left", padx=(8, 0))
        ctk.CTkButton(bar, text="Entfernen", width=90, image=style.icon("trash-2"),
                      **style.secondary(),
                      command=lambda: self._set_logo("")).pack(side="left", padx=8)
        ctk.CTkLabel(tab, text="Oder ein Bild aus dem Explorer ins Fenster ziehen bzw. mit Strg+V "
                               "aus der Zwischenablage einfügen.",
                     text_color=style.MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=4)
        self.logo_name = ctk.CTkLabel(tab, text="Kein Logo gewählt", anchor="w",
                                      text_color=style.MUTED)
        self.logo_name.pack(fill="x", padx=4)
        self._on_refresh(self._refresh_logo_name)

        section(tab, "Größe und Unterlage")
        self._slider(tab, "Größe", "logo_size", 10, 30, steps=20, scale=100,
                     fmt=lambda v: f"{v:.0f} %")
        self.logo_warn = ctk.CTkLabel(tab, text="", text_color=style.WARN,
                                      anchor="w", wraplength=380, justify="left")
        self.logo_warn.pack(fill="x", padx=4)
        self._on_refresh(self._refresh_logo_warn)
        self._switch(tab, "Unterlage", "logo_plate")
        self._color(tab, "Unterlagenfarbe", "logo_plate_color")
        self._slider(tab, "Eckenradius", "logo_radius", 0, 50, steps=50, scale=100,
                     fmt=lambda v: f"{v:.0f} %")
        self._slider(tab, "Innenabstand", "logo_padding", 0, 30, steps=30, scale=100,
                     fmt=lambda v: f"{v:.0f} %")
        ctk.CTkLabel(tab, text="Tipp: PNG mit transparentem Hintergrund sieht am besten aus. "
                               "Unter dem Logo werden die Module ausgespart; die "
                               "Fehlerkorrektur H gleicht das aus.",
                     text_color=style.MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=4, pady=(12, 0))

    def _pick_logo(self) -> None:
        path = filedialog.askopenfilename(title="Logo wählen", filetypes=LOGO_TYPES)
        if path:
            self._set_logo(path)

    def _paste_logo_clicked(self) -> None:
        if not self.paste_logo():
            messagebox.showinfo("Logo einfügen", "In der Zwischenablage ist kein Bild.", parent=self)

    def paste_logo(self) -> bool:
        """Logo aus der Zwischenablage (Bild oder kopierte Bilddatei). True, wenn eines da war."""
        import time

        from PIL import ImageGrab

        from ..core.userdir import user_dir

        try:
            clip = ImageGrab.grabclipboard()
        except Exception:
            return False
        if isinstance(clip, list):
            files = [f for f in clip if os.path.splitext(f)[1].lower() in LOGO_SUFFIXES]
            if files:
                self._set_logo(files[0])
                return True
            return False
        if clip is None:
            return False
        folder = user_dir() / "logos"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / time.strftime("zwischenablage-%Y%m%d-%H%M%S.png")
        clip.save(path, "PNG")
        self._set_logo(str(path))
        return True

    def _set_logo(self, path: str) -> None:
        self.d.logo_path = path
        if path and self.d.ecc != "H":
            self.d.ecc = "H"
            self.refresh()
        self._refresh_logo_name()
        self.app.changed()

    def _refresh_logo_name(self) -> None:
        p = self.d.logo_path
        self.logo_name.configure(text=os.path.basename(p) if p else "Kein Logo gewählt")

    def _refresh_logo_warn(self) -> None:
        self.logo_warn.configure(text="Über 25 % wird es für Scanner knapp – die Scan-Prüfung "
                                      "rechts zeigt, ob es noch reicht."
                                 if self.d.logo_size > 0.25 else "")

    # ================================================================ Beschriftung

    def _build_caption(self, tab) -> None:
        section(tab, "Rahmen")
        self._choice(tab, "Stil", "frame", FRAME_LABELS)
        self._color(tab, "Rahmenfarbe", "frame_color")
        self._color(tab, "Pfeilfarbe", "arrow_color")
        ctk.CTkLabel(tab, text="Die Pfeilfarbe gilt für „Handschrift mit Pfeil“.",
                     text_color=style.MUTED, anchor="w").pack(fill="x", padx=4)

        section(tab, "Text")
        box = ctk.CTkTextbox(tab, height=64, wrap="word")
        box.pack(fill="x", padx=4, pady=4)
        box.insert("1.0", self.d.caption)
        box.bind("<KeyRelease>", lambda _e: self._set("caption", box.get("1.0", "end-1c")))

        def refresh_box():
            if box.get("1.0", "end-1c") != self.d.caption:
                box.delete("1.0", "end")
                box.insert("1.0", self.d.caption)
        self._on_refresh(refresh_box)
        ctk.CTkLabel(tab, text="Zeilenumbruch mit Enter ergibt zwei Zeilen.",
                     text_color=style.MUTED, anchor="w").pack(fill="x", padx=4)
        self._choice(tab, "Position", "caption_position", POSITION_LABELS)
        ctk.CTkLabel(tab, text="Die Banner haben ihre Position im Namen; beim Pfeil dreht "
                               "sich die Richtung mit.", text_color=style.MUTED, anchor="w",
                     justify="left", wraplength=380).pack(fill="x", padx=4)

        section(tab, "Schrift")
        families = fonts.families()
        font_menu = ctk.CTkOptionMenu(row(tab, "Schriftart"), values=families,
                                      command=self._font_changed, dynamic_resizing=False,
                                      width=220)
        font_menu.grid(row=0, column=1, sticky="ew")
        self.font_preview = ctk.CTkLabel(tab, text="", height=48, anchor="w")
        self.font_preview.pack(fill="x", padx=8)

        def refresh_font():
            fam = self.d.caption_font if self.d.caption_font in families else families[0]
            font_menu.set(fam)
            self._show_font_preview()
        self._on_refresh(refresh_font)
        refresh_font()

        self._switch(tab, "Fett", "caption_bold")
        self._slider(tab, "Größe", "caption_size", 30, 100, steps=70, as_int=True,
                     fmt=lambda v: f"{v:.0f} %")
        self._color(tab, "Textfarbe", "caption_color")

    def _font_changed(self, family: str) -> None:
        self.d.caption_font = family
        self._show_font_preview()
        self.app.changed()

    def _show_font_preview(self) -> None:
        sample = (self.d.caption.strip().splitlines() or ["SCAN ME – Beispiel 123"])[0]
        self.font_preview.configure(
            text=sample, font=ctk.CTkFont(family=self.d.caption_font, size=24,
                                          weight="bold" if self.d.caption_bold else "normal"))

    # ================================================================ Export

    def _build_export(self, tab) -> None:
        section(tab, "Format")
        self.fmt = ctk.CTkSegmentedButton(tab, values=list(export.FORMATS))
        self.fmt.set("PNG")
        self.fmt.pack(anchor="w", padx=4, pady=4)
        ctk.CTkLabel(tab, text="PNG für Web und Office, SVG für Grafikprogramme, PDF für den "
                               "Druck. SVG und PDF sind Vektorgrafiken und in jeder Größe scharf; "
                               "beim PDF legen Breite und dpi nur die Seitengröße fest.",
                     text_color=style.MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=4)

        section(tab, "Auflösung")
        self.size = ctk.CTkOptionMenu(row(tab, "Breite"),
                                      values=["512 px", "1024 px", "2048 px", "4096 px"], width=140)
        self.size.set("1024 px")
        self.size.grid(row=0, column=1, sticky="w")
        self.dpi = ctk.CTkOptionMenu(row(tab, "Druckauflösung"),
                                     values=["150 dpi", "300 dpi", "600 dpi"], width=140)
        self.dpi.set("300 dpi")
        self.dpi.grid(row=0, column=1, sticky="w")

        ctk.CTkButton(tab, text="QR-Code speichern …", height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      image=style.icon("download", accent=True, size=20), **style.primary(),
                      command=self.save).pack(fill="x", padx=4, pady=(24, 6))
        ctk.CTkButton(tab, text="In die Zwischenablage kopieren (Strg+C)",
                      image=style.icon("clipboard-copy"), **style.secondary(),
                      command=self.copy).pack(fill="x", padx=4, pady=(0, 6))
        self.export_status = ctk.CTkLabel(tab, text="", anchor="w", wraplength=380,
                                          justify="left")
        self.export_status.pack(fill="x", padx=4)

        if self.fixed_payload is not None:
            return  # ein fester Inhalt -- eine Liste vieler Inhalte passt nicht dazu
        section(tab, "Stapel-Export")
        ctk.CTkLabel(tab, text="Viele Codes im aktuellen Design auf einmal: eine CSV-Liste "
                               "(z. B. aus Excel) mit dem Inhalt in der ersten Spalte, optional dem "
                               "Dateinamen in der zweiten. Format, Breite und dpi von oben.",
                     text_color=style.MUTED, anchor="w", justify="left",
                     wraplength=380).pack(fill="x", padx=4)
        self.batch_check = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(tab, text="Jeden Code auf Lesbarkeit prüfen",
                        variable=self.batch_check).pack(anchor="w", padx=4, pady=6)
        self.batch_button = ctk.CTkButton(tab, text="CSV-Liste wählen …",
                                          image=style.icon("file-spreadsheet"), command=self.batch_export)
        self.batch_button.pack(fill="x", padx=4)
        self.batch_status = ctk.CTkLabel(tab, text="", anchor="w", wraplength=380, justify="left")
        self.batch_status.pack(fill="x", padx=4, pady=(4, 0))

    def _export_size(self) -> tuple[int, int]:
        return int(self.size.get().split()[0]), int(self.dpi.get().split()[0])

    def save(self) -> None:
        if self.app.preview.readable is False and not messagebox.askyesno(
                "Scan-Prüfung nicht bestanden",
                "Der Code hat die Scan-Prüfung nicht bestanden und lässt sich mit vielen Handys "
                "vermutlich nicht lesen.\n\nTrotzdem speichern?", icon="warning", parent=self):
            return
        fmt = self.fmt.get()
        ext = export.FORMATS[fmt]
        path = filedialog.asksaveasfilename(title="QR-Code speichern", defaultextension=ext,
                                            initialfile=getattr(self.app, "export_name", "qr-code") + ext,
                                            filetypes=[(fmt, "*" + ext)])
        if not path:
            return
        width, dpi = self._export_size()
        # Grosse Breiten brauchen ein paar Sekunden -- vorher Bescheid geben
        self.export_status.configure(text=f"Speichere {width} px …", text_color=style.MUTED)
        self.app.configure(cursor="watch")
        self.update_idletasks()
        try:
            out = export.save(self.d, path, width_px=width, dpi=dpi)
        except Exception as exc:
            self.export_status.configure(text="")
            messagebox.showerror("Speichern fehlgeschlagen", str(exc), parent=self)
            return
        finally:
            self.app.configure(cursor="")
        self.export_status.configure(text=f"✓ Gespeichert: {out}",
                                     text_color=style.ACCENT)

    def copy(self) -> None:
        from ..core import clipboard
        from ..core.render_pil import render as render_img

        width, _ = self._export_size()
        try:
            img = render_img(self.d, width)
            if not self.d.transparent_bg:
                img = img.convert("RGB")
            clipboard.copy_image(img, self.d.bg_color)
        except Exception as exc:
            messagebox.showerror("Kopieren fehlgeschlagen", str(exc), parent=self)
            return
        self.export_status.configure(text=f"✓ In die Zwischenablage kopiert ({width} px) – "
                                          "z. B. mit Strg+V in Word einfügen",
                                     text_color=style.ACCENT)

    def batch_export(self, csv_path: str | None = None) -> None:
        import threading

        from ..core import batch

        csv_path = csv_path or filedialog.askopenfilename(
            title="CSV-Liste wählen", filetypes=[("CSV", "*.csv *.txt"), ("Alle Dateien", "*.*")])
        if not csv_path:
            return
        try:
            rows = batch.read_rows(csv_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Stapel-Export", f"Die Liste ließ sich nicht lesen:\n{exc}", parent=self)
            return
        if not rows:
            messagebox.showinfo("Stapel-Export", "In der Liste steht kein Inhalt.", parent=self)
            return
        folder = filedialog.askdirectory(title=f"Zielordner für {len(rows)} QR-Codes",
                                         initialdir=os.path.dirname(csv_path))
        if not folder:
            return
        fmt = self.fmt.get()
        width, dpi = self._export_size()
        design = self.d
        check = self.batch_check.get()
        self.batch_button.configure(state="disabled")

        def progress(done, total):
            self.after(0, lambda: self.batch_status.configure(
                text=f"{done} von {total} …", text_color=style.MUTED))

        def work():
            try:
                files, bad = batch.export_all(design, rows, folder, export.FORMATS[fmt], width, dpi,
                                              check, progress)
                self.after(0, lambda: finish(files, bad, None))
            except Exception as exc:  # Fehler in die Oberflaeche melden
                self.after(0, lambda e=exc: finish([], [], e))

        def finish(files, bad, error):
            self.batch_button.configure(state="normal")
            if error is not None:
                self.batch_status.configure(text="")
                messagebox.showerror("Stapel-Export", f"Abgebrochen:\n{error}", parent=self)
                return
            text = f"✓ {len(files)} Codes gespeichert in {folder}"
            color = style.ACCENT
            if bad:
                text += f"\n⚠ {len(bad)} nicht lesbar: " + ", ".join(bad[:5]) + (" …" if len(bad) > 5 else "")
                color = style.WARN
            self.batch_status.configure(text=text, text_color=color)

        threading.Thread(target=work, daemon=True).start()

    # ================================================================ Zustand

    def content_state(self) -> dict:
        """Inhaltstyp und Formularwerte (fuer den naechsten Start)."""
        if self.fixed_payload is not None:
            return {}
        return {"type": self.content_type,
                "values": {t: {k: v.get() for k, v in store.items()} for t, store in self._values.items()}}

    def restore_content(self, state: dict) -> None:
        if self.fixed_payload is not None:
            self._update_payload()
            return
        ctype = state.get("type")
        for t, values in (state.get("values") or {}).items():
            if t not in FIELDS or not isinstance(values, dict):
                continue
            kinds = {k: kind for k, _l, kind in FIELDS[t]}
            for k, value in values.items():
                if k in kinds:
                    var = self._var(t, k, kinds[k])
                    var.set(bool(value) if kinds[k] == "switch" else str(value))
        if ctype in FIELDS:
            self.content_type = ctype
            self.content_choice.set_key(ctype)
            self._build_form()
        self._update_payload()
