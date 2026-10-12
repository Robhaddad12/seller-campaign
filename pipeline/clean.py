"""Reads Vulcan7 CSV files and turns them into clean, de-duplicated leads."""

import configparser
import csv
import re

# ---------------------------------------------------------------- settings

def load_settings(path):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None)
    with open(path, encoding="utf-8") as f:
        parser.read_file(f)

    def get(section, key, default=""):
        return parser.get(section, key, fallback=default).strip()

    def options(section, key):
        return [o.strip() for o in get(section, key).split("|") if o.strip()]

    columns = {
        name: options("columns", name)
        for name in ("first_name", "last_name", "full_name", "property_address", "city", "state", "zip")
    }
    columns["email_columns"] = options("columns", "email_columns")

    return {
        "campaign_id": get("smartlead", "campaign_id"),
        "inbox_folder": get("folders", "inbox_folder", "vulcan7-inbox"),
        "emails_per_owner": get("choices", "emails_per_owner", "first").lower(),
        "companies_and_trusts": get("choices", "companies_and_trusts", "keep").lower(),
        "company_first_name": get("choices", "company_first_name", "Homeowner"),
        "full_name_order": get("columns", "full_name_order", "first_last").lower(),
        "columns": columns,
    }


# ---------------------------------------------------------------- reading

def read_csv(path):
    """Returns (headers, rows). Copes with Excel's odd text encodings."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                return reader.fieldnames or [], rows
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not read %s. Re-export it from Vulcan7 as a CSV file." % path)


def _simplify(heading):
    return re.sub(r"[^a-z0-9]", "", (heading or "").lower())


def match_columns(headers, column_settings):
    """Works out which real column heading to use for each field.

    Returns ({field: heading or None}, [email headings found, in preference order]).
    """
    by_simple = {}
    for h in headers:
        by_simple.setdefault(_simplify(h), h)

    found = {}
    for field, candidates in column_settings.items():
        if field == "email_columns":
            continue
        found[field] = next((by_simple[_simplify(c)] for c in candidates if _simplify(c) in by_simple), None)

    emails = []
    for c in column_settings["email_columns"]:
        h = by_simple.get(_simplify(c))
        if h and h not in emails:
            emails.append(h)
    return found, emails


# ---------------------------------------------------------------- names

COMPANY_WORDS = re.compile(
    r"\b(LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|COMPANY|LP|LLP|LTD|TRUST|TRUSTS|TRUSTEE|TRUSTEES|TR|TRS|"
    r"ESTATE|BANK|HOLDINGS|PROPERTIES|INVESTMENTS?|CAPITAL|VENTURES|PARTNERS|PARTNERSHIP|GROUP|"
    r"ASSOCIATION|ASSN|HOA|CHURCH|MINISTRIES|FOUNDATION|REALTY|DEVELOPMENT|ENTERPRISES|REVOCABLE|"
    r"FUND|MORTGAGE|FEDERAL|NATIONAL|COUNTY|CITY OF|STATE OF|HOUSING|AUTHORITY)\b",
    re.IGNORECASE,
)
SUFFIXES = {"JR", "SR", "II", "III", "IV", "ETAL", "MD", "DDS", "PHD", "ESQ"}
ET_AL = re.compile(r"\bet\.?\s*al\.?(?=\s|$)", re.IGNORECASE)
CO_OWNER_SPLIT = re.compile(r"\s*(?:&|\band\b|/|\+)\s*", re.IGNORECASE)


def is_company(name):
    return bool(name and COMPANY_WORDS.search(name))


def _cap_word(word):
    if not word:
        return word
    if word.upper() in {"II", "III", "IV"}:
        return word.upper()
    w = word[0].upper() + word[1:].lower()
    if len(w) > 2 and w.startswith("Mc"):
        w = "Mc" + w[2].upper() + w[3:]
    return w


def tidy_name(name):
    """'mcDONALD-o'brien' -> "McDonald-O'Brien"."""
    name = re.sub(r"\s+", " ", (name or "").strip(" ,.;"))
    parts = re.split(r"([ \-'])", name)
    return "".join(_cap_word(p) if p not in (" ", "-", "'") else p for p in parts)


def _real_words(text):
    text = ET_AL.sub(" ", text)
    words = [w for w in re.split(r"\s+", text.replace(".", " ").strip()) if w]
    return [w for w in words if w.upper().replace(".", "") not in SUFFIXES]


def first_word(text):
    """First real name from a first-name cell: 'JOHN A & MARY' -> 'John'."""
    first_owner = CO_OWNER_SPLIT.split(text.strip())[0]
    words = [w for w in _real_words(first_owner) if len(w) > 1]  # skip initials
    return tidy_name(words[0]) if words else ""


def split_full_name(full, order):
    """Returns (first, last) from a single owner-name cell."""
    full = re.sub(r"\s+", " ", (full or "").strip())
    if not full:
        return "", ""
    if "," in full:
        last, rest = full.split(",", 1)
        return first_word(rest), tidy_name(" ".join(_real_words(last)))

    owners = CO_OWNER_SPLIT.split(full)
    if order == "last_first":
        words = _real_words(owners[0])
        last = words[0] if words else ""
        firsts = [w for w in words[1:] if len(w) > 1]
        first = firsts[0] if firsts else ""
        return tidy_name(first), tidy_name(last)

    # first_last: "John & Mary Smith" -> John / Smith
    first = first_word(owners[0])
    last_words = _real_words(owners[-1])
    last = last_words[-1] if len(last_words) > 1 else ""
    if len(owners) == 1 and len(last_words) <= 1:
        last = ""
    return first, tidy_name(last)


# ---------------------------------------------------------------- emails

EMAIL_OK = re.compile(r"^[a-z0-9._%+\-']+@[a-z0-9.\-]+\.[a-z]{2,}$")


def emails_from_row(row, email_headings):
    good, bad = [], []
    for h in email_headings:
        for piece in re.split(r"[;,\s]+", row.get(h) or ""):
            e = piece.strip().strip("<>").lower()
            if e.startswith("mailto:"):
                e = e[7:]
            if not e:
                continue
            if EMAIL_OK.match(e) and ".." not in e:
                if e not in good:
                    good.append(e)
            else:
                bad.append(e)
    return good, bad


# ---------------------------------------------------------------- addresses

DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
    "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}


def tidy_address(address):
    """'1234 N MAIN ST APT 5b' -> '1234 N Main St Apt 5B'."""
    words = re.sub(r"\s+", " ", (address or "").strip(" ,")).split(" ")
    out = []
    for w in words:
        bare = w.upper().strip(".,")
        if bare in DIRECTIONS or bare in {"PO", "US", "SR"}:
            out.append(w.upper())
        elif re.match(r"^\d+(ST|ND|RD|TH)$", bare):
            out.append(w.lower())
        elif any(ch.isdigit() for ch in w):
            out.append(w.upper())
        else:
            out.append(tidy_name(w))
    return " ".join(out)


def tidy_city(city):
    return " ".join(tidy_name(w) for w in re.sub(r"\s+", " ", (city or "").strip(" ,")).split(" ") if w)


def tidy_state(state):
    s = re.sub(r"\s+", " ", (state or "").strip(" .,")).upper()
    return STATES.get(s, s)


def tidy_zip(z):
    digits = re.sub(r"\D", "", (z or "").split("-")[0])
    if 3 <= len(digits) <= 4:  # Excel drops leading zeros
        digits = digits.zfill(5)
    return digits[:5]


# ---------------------------------------------------------------- the scrub

def scrub(files, settings, already_loaded):
    """Turns raw CSV rows into clean leads.

    files: list of (file_name, headers, rows, column_match, email_headings)
    already_loaded: {email: date first loaded}
    Returns (leads, removed). Each removed item says why.
    """
    leads, removed = [], []
    seen_emails = set()
    seen_properties = set()
    order = settings["full_name_order"]

    for file_name, _headers, rows, cols, email_headings in files:
        def cell(row, field):
            h = cols.get(field)
            return (row.get(h) or "").strip() if h else ""

        for i, row in enumerate(rows, start=2):  # row 1 is the headings
            raw_name = cell(row, "full_name") or " ".join(
                p for p in (cell(row, "first_name"), cell(row, "last_name")) if p
            )
            address = tidy_address(cell(row, "property_address"))
            where = {"file": file_name, "row": i, "owner": raw_name, "property_address": address}

            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue  # completely blank line

            company = is_company(raw_name)
            if company and settings["companies_and_trusts"] == "skip":
                removed.append(dict(where, reason="Company or trust (settings say skip)"))
                continue

            good, bad = emails_from_row(row, email_headings)
            if not good:
                reason = "No email address" if not bad else "Email address not valid: " + ", ".join(bad)
                removed.append(dict(where, reason=reason))
                continue

            if not address:
                removed.append(dict(where, reason="No property address (your emails need it)"))
                continue

            property_key = (address.lower(), cell(row, "city").lower(), tidy_zip(cell(row, "zip")))
            if settings["emails_per_owner"] != "all" and property_key in seen_properties:
                removed.append(dict(where, reason="Duplicate (same property earlier in today's files)"))
                continue
            seen_properties.add(property_key)

            if company:
                first, last = settings["company_first_name"], ""
            else:
                first = first_word(cell(row, "first_name")) if cell(row, "first_name") else ""
                last = tidy_name(" ".join(_real_words(cell(row, "last_name")))) if cell(row, "last_name") else ""
                if not first or not last:
                    f2, l2 = split_full_name(cell(row, "full_name"), order)
                    first, last = first or f2, last or l2
                first = first or settings["company_first_name"]

            targets = good if settings["emails_per_owner"] == "all" else good[:1]
            for email in targets:
                info = dict(where, email=email)
                if email in already_loaded:
                    removed.append(dict(info, reason="Already sent to Smartlead on " + already_loaded[email]))
                    continue
                if email in seen_emails:
                    removed.append(dict(info, reason="Duplicate (same email earlier in today's files)"))
                    continue
                seen_emails.add(email)
                leads.append({
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "property_address": address,
                    "city": tidy_city(cell(row, "city")),
                    "state": tidy_state(cell(row, "state")),
                    "zip": tidy_zip(cell(row, "zip")),
                    "is_company_or_trust": "yes" if company else "",
                    "source_file": file_name,
                    "source_row": i,
                })

    return leads, removed
