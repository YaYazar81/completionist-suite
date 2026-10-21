"""Erzeugt den Text, der im QR-Code steckt, für die unterstützten Inhaltstypen."""
from __future__ import annotations

import re
from urllib.parse import quote


def _wifi_escape(value: str) -> str:
    for ch in ("\\", ";", ",", ":", '"'):
        value = value.replace(ch, "\\" + ch)
    return value


def _vcard_escape(value: str) -> str:
    return (value.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def url(value: str) -> str:
    value = value.strip()
    if value and "://" not in value and "." in value and " " not in value:
        value = "https://" + value
    return value


def text(value: str) -> str:
    return value


def wifi(ssid: str, password: str = "", security: str = "WPA", hidden: bool = False) -> str:
    security = security if security in ("WPA", "WEP", "nopass") else "WPA"
    parts = [f"T:{security}", f"S:{_wifi_escape(ssid)}"]
    if security != "nopass":
        parts.append(f"P:{_wifi_escape(password)}")
    if hidden:
        parts.append("H:true")
    return "WIFI:" + ";".join(parts) + ";;"


def vcard(first: str = "", last: str = "", org: str = "", title: str = "", phone: str = "",
          email: str = "", street: str = "", city: str = "", zip_code: str = "",
          country: str = "", website: str = "") -> str:
    e = _vcard_escape
    full = " ".join(p for p in (first, last) if p)
    lines = ["BEGIN:VCARD", "VERSION:3.0",
             f"N:{e(last)};{e(first)};;;", f"FN:{e(full)}"]
    if org:
        lines.append(f"ORG:{e(org)}")
    if title:
        lines.append(f"TITLE:{e(title)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{phone}")
    if email:
        lines.append(f"EMAIL:{email}")
    if any((street, city, zip_code, country)):
        lines.append(f"ADR;TYPE=WORK:;;{e(street)};{e(city)};;{e(zip_code)};{e(country)}")
    if website:
        lines.append(f"URL:{url(website)}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def email(address: str, subject: str = "", body: str = "") -> str:
    params = []
    if subject:
        params.append("subject=" + quote(subject))
    if body:
        params.append("body=" + quote(body))
    return f"mailto:{address}" + ("?" + "&".join(params) if params else "")


def phone(number: str) -> str:
    return "tel:" + number.replace(" ", "")


def sms(number: str, message: str = "") -> str:
    return f"SMSTO:{number.replace(' ', '')}:{message}"


def geo(lat: str, lon: str) -> str:
    return f"geo:{float(lat.replace(',', '.'))},{float(lon.replace(',', '.'))}"


def maps(lat: str = "", lon: str = "", address: str = "") -> str:
    """Kartenlink, den jede Handykamera oeffnet (geo: kennt iOS nicht).

    Mit Adresse eine Suche, sonst die Koordinaten."""
    if address.strip():
        return "https://www.google.com/maps/search/?api=1&query=" + quote(address.strip())
    la, lo = float(lat.replace(",", ".")), float(lon.replace(",", "."))
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        raise ValueError("Bitte gültige Koordinaten eingeben (Breite −90…90, Länge −180…180).")
    return f"https://www.google.com/maps/search/?api=1&query={la},{lo}"


# ---------------------------------------------------------------------- #
# Zahlung
# ---------------------------------------------------------------------- #


def iban_valid(iban: str) -> bool:
    """Pruefziffer nach ISO 13616 (Modulo 97)."""
    s = re.sub(r"\s+", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    digits = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(digits) % 97 == 1


def _amount(value: str) -> str:
    """"12,5" -> "12.50"; leer -> "". Wirft ValueError bei Unsinn."""
    v = value.strip().replace("€", "").replace(" ", "")
    if not v:
        return ""
    if "," in v:
        v = v.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
    amount = float(v)
    if not 0.01 <= amount <= 999_999_999.99:
        raise ValueError("Bitte einen Betrag zwischen 0,01 und 999.999.999,99 € eingeben.")
    return f"{amount:.2f}"


def epc(name: str, iban: str, amount: str = "", purpose: str = "", bic: str = "") -> str:
    """SEPA-Ueberweisung als GiroCode/EPC-QR (European Payments Council, Version 002).

    Deutsche Banking-Apps uebernehmen damit Empfaenger, IBAN, Betrag und
    Verwendungszweck. Der Standard verlangt UTF-8 und hoechstens 331 Byte.
    """
    name = " ".join(name.split())
    if not name:
        raise ValueError("Bitte den Namen des Empfängers eingeben.")
    if len(name) > 70:
        raise ValueError("Der Empfängername darf höchstens 70 Zeichen haben.")
    iban_c = re.sub(r"\s+", "", iban).upper()
    if not iban_valid(iban_c):
        raise ValueError("Die IBAN ist ungültig (Prüfziffer stimmt nicht).")
    purpose = " ".join(purpose.split())
    if len(purpose) > 140:
        raise ValueError("Der Verwendungszweck darf höchstens 140 Zeichen haben.")
    amt = _amount(amount)
    lines = ["BCD", "002", "1", "SCT", re.sub(r"\s+", "", bic).upper(), name, iban_c,
             f"EUR{amt}" if amt else "", "", "", purpose]
    return "\n".join(lines).rstrip("\n")


def paypal(user: str, amount: str = "") -> str:
    user = user.strip().lstrip("@")
    user = re.sub(r"^(https?://)?(www\.)?paypal\.me/", "", user, flags=re.I).strip("/")
    if not user:
        raise ValueError("Bitte den PayPal.me-Namen eingeben.")
    amt = _amount(amount)
    return f"https://paypal.me/{quote(user)}" + (f"/{amt}EUR" if amt else "")


# ---------------------------------------------------------------------- #
# Messenger und soziale Netzwerke
# ---------------------------------------------------------------------- #


def whatsapp(number: str, message: str = "") -> str:
    """Chat oeffnen (wa.me). Nummer international, ohne + und Leerzeichen."""
    digits = re.sub(r"\D", "", number.replace("+", ""))
    if number.strip().startswith("0") and not number.strip().startswith("00"):
        digits = "49" + digits.lstrip("0")  # 0170 ... -> 49170 ... (Deutschland)
    elif digits.startswith("00"):
        digits = digits[2:]
    if len(digits) < 7:
        raise ValueError("Bitte die Handynummer eingeben, z. B. +49 170 1234567.")
    return f"https://wa.me/{digits}" + (f"?text={quote(message)}" if message else "")


SOCIAL = {
    "instagram": ("Instagram", "https://www.instagram.com/{}"),
    "facebook": ("Facebook", "https://www.facebook.com/{}"),
    "tiktok": ("TikTok", "https://www.tiktok.com/@{}"),
    "youtube": ("YouTube", "https://www.youtube.com/@{}"),
    "x": ("X (Twitter)", "https://x.com/{}"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/in/{}"),
    "threads": ("Threads", "https://www.threads.net/@{}"),
    "twitch": ("Twitch", "https://www.twitch.tv/{}"),
    "pinterest": ("Pinterest", "https://www.pinterest.com/{}"),
    "github": ("GitHub", "https://github.com/{}"),
}


def social(platform: str, handle: str) -> str:
    """Profil-Link aus Plattform und Benutzername (oder fertigem Link)."""
    handle = handle.strip()
    if not handle:
        raise ValueError("Bitte den Benutzernamen oder Profil-Link eingeben.")
    if "://" in handle or handle.lower().startswith("www."):
        return url(handle)
    _, pattern = SOCIAL.get(platform, SOCIAL["instagram"])
    return pattern.format(quote(handle.lstrip("@")))


def feedback(link: str = "", address: str = "", subject: str = "Feedback") -> str:
    """Link zu einem Formular (z. B. Google Forms) oder ersatzweise eine E-Mail."""
    if link.strip():
        return url(link)
    if address.strip():
        return email(address.strip(), subject or "Feedback")
    raise ValueError("Bitte einen Formular-Link oder eine E-Mail-Adresse eingeben.")
