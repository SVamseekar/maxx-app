"""Recognise a tracking number and check its check digit, offline, before anyone is paid.

The patterns and checksum rules come from the MIT-licensed tracking_number_data project
(github.com/jkeen/tracking_number_data, commit 03af203), vendored under `carriers/`. Each courier
file ships valid and invalid sample numbers, and the test suite runs every one of them through
this module, so the algorithms here are checked against the data's own expectations.

A number passing here only proves it is well-formed for that carrier. Whether a parcel exists is
the tracking provider's job (see `tracking.py`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CARRIERS_DIR = Path(__file__).with_name("carriers")

# The carriers a seller can choose, mapped to the courier files that describe their numbers.
CARRIERS: dict[str, dict] = {
    "ups": {"label": "UPS", "files": ["ups"]},
    "usps": {"label": "USPS", "files": ["usps"]},
    "fedex": {"label": "FedEx", "files": ["fedex"]},
    "dhl": {"label": "DHL", "files": ["dhl"]},
    "canadapost": {"label": "Canada Post", "files": ["canadapost", "s10"]},
    "royalmail": {"label": "Royal Mail", "files": ["s10"]},
    "postal": {"label": "Another national post (UPU S10)", "files": ["s10"]},
    "dpd": {"label": "DPD", "files": ["dpd"]},
    "ontrac": {"label": "OnTrac", "files": ["ontrac"]},
    "amazon": {"label": "Amazon Logistics", "files": ["amazon"]},
    "purolator": {"label": "Purolator", "files": ["purolator"]},
    "yodel": {"label": "Yodel", "files": ["yodel"]},
    "lasership": {"label": "LaserShip", "files": ["lasership"]},
    "other": {"label": "Other carrier", "files": []},
}


@dataclass(frozen=True)
class Recognised:
    carrier: str
    kind: str  # the courier file's name for this number format, e.g. "UPS" or "USPS IMpb N"
    number: str  # normalised: upper case, no spaces
    checksum: bool  # True when the format has a check digit and it matched


def _python_regex(pattern) -> re.Pattern:
    text = "".join(pattern) if isinstance(pattern, list) else pattern
    # The data is written for PCRE/Ruby: named groups are (?<name>...) instead of (?P<name>...).
    text = re.sub(r"\(\?<(?![=!])", "(?P<", text)
    return re.compile(text)


@lru_cache
def _formats(name: str) -> list[dict]:
    data = json.loads((CARRIERS_DIR / f"{name}.json").read_text())
    formats = []
    for entry in data["tracking_numbers"]:
        formats.append(
            {
                "name": entry["name"],
                "regex": _python_regex(entry["regex"]),
                "validation": entry.get("validation") or {},
                "tests": entry.get("test_numbers") or {},
                "lookups": {
                    item["name"]: (item["regex_group_name"], item["lookup"])
                    for item in entry.get("additional") or []
                },
            }
        )
    return formats


def _lookups_exist(fmt: dict, match: re.Match) -> bool:
    """Some formats require a part to be a known value, e.g. an S10 number's two-letter country
    must belong to a real postal operator."""
    required = ((fmt["validation"] or {}).get("additional") or {}).get("exists") or []
    for name in required:
        group, table = fmt["lookups"].get(name, (None, []))
        value = _digits(match.groupdict().get(group) or "") if group else ""
        if not any(
            row.get("matches") == value
            or ("matches_regex" in row and re.fullmatch(row["matches_regex"], value))
            for row in table
        ):
            return False
    return True


def _digits(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _mod10(sequence: str, check: str, rule: dict) -> bool:
    total = 0
    for index, char in enumerate(sequence):
        value = int(char) if char.isdigit() else (ord(char) - 3) % 10
        if index % 2 == 1 and rule.get("odds_multiplier"):
            value *= int(rule["odds_multiplier"])
        elif index % 2 == 0 and rule.get("evens_multiplier"):
            value *= int(rule["evens_multiplier"])
        total += value
    remainder = total % 10
    expected = 0 if remainder == 0 else 10 - remainder
    return check.isdigit() and expected == int(check)


def _mod7(sequence: str, check: str, rule: dict) -> bool:
    return sequence.isdigit() and check.isdigit() and int(sequence) % 7 == int(check)


def _s10(sequence: str, check: str, rule: dict) -> bool:
    weights = rule.get("weightings") or [8, 6, 4, 2, 3, 5, 9, 7]
    if not sequence.isdigit() or not check.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(sequence, weights, strict=False))
    remainder = total % 11
    expected = 0 if remainder == 1 else 5 if remainder == 0 else 11 - remainder
    return expected == int(check)


def _weighted(sequence: str, check: str, rule: dict) -> bool:
    if not sequence.isdigit() or not check.isdigit():
        return False
    total = sum(int(d) * int(w) for d, w in zip(sequence, rule["weightings"], strict=False))
    return total % int(rule["modulo1"]) % int(rule["modulo2"]) == int(check)


def _luhn(sequence: str, check: str, rule: dict) -> bool:
    if not sequence.isdigit() or not check.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(sequence)):
        value = int(char)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    remainder = total % 10
    expected = 0 if remainder == 0 else 10 - remainder
    return expected == int(check)


def _mod_37_36(sequence: str, check: str, rule: dict) -> bool:
    """ISO/IEC 7064 MOD 37,36 (used by DPD)."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    modulus = 36
    product = modulus
    for char in sequence:
        if char not in alphabet:
            return False
        product = (product + alphabet.index(char)) % modulus or modulus
        product = (product * 2) % (modulus + 1)
    expected = (modulus + 1 - product) % modulus
    return alphabet[expected] == check


CHECKSUMS = {
    "mod10": _mod10,
    "mod7": _mod7,
    "s10": _s10,
    "sum_product_with_weightings_and_modulo": _weighted,
    "luhn": _luhn,
    "mod_37_36": _mod_37_36,
}


def _check(fmt: dict, match: re.Match) -> bool | None:
    """True or False when the format has a checksum, None when it has none to check."""
    rule = (fmt["validation"] or {}).get("checksum")
    if not rule:
        return None
    groups = match.groupdict()
    serial = _digits(groups.get("SerialNumber") or "")
    check = _digits(groups.get("CheckDigit") or "")
    prepend = (fmt["validation"].get("serial_number_format") or {}).get("prepend_if")
    if prepend and re.match(_python_regex(prepend["matches_regex"]), serial):
        serial = prepend["content"] + serial
    algorithm = CHECKSUMS.get(rule["name"])
    if algorithm is None or not serial or not check:
        return False
    return algorithm(serial, check, rule)


def match_format(fmt: dict, raw: str) -> bool | None:
    """None if the text is not this format; otherwise whether it passes its validation."""
    text = raw.strip().upper()
    match = fmt["regex"].fullmatch(text)
    if not match:
        return None
    if not _lookups_exist(fmt, match):
        return False
    result = _check(fmt, match)
    return True if result is None else result


def recognise(carrier: str, raw: str) -> Recognised | None:
    """The format a seller-entered number matches for that carrier, with its check digit verified.

    Returns None if it matches no known format for the carrier, or matches one whose check digit
    is wrong (the most common sign of a typo, or of a made-up number).
    """
    info = CARRIERS.get(carrier)
    if info is None or not info["files"] or not raw or len(raw) > 80:
        return None
    for name in info["files"]:
        for fmt in _formats(name):
            result = match_format(fmt, raw)
            if result:
                has_checksum = bool((fmt["validation"] or {}).get("checksum"))
                return Recognised(carrier, fmt["name"], _digits(raw).upper(), has_checksum)
    return None


def normalise(raw: str) -> str:
    return _digits(raw).upper()


def all_formats() -> list[tuple[str, dict]]:
    """Every vendored format with its test numbers (used by the test suite)."""
    names = sorted(p.stem for p in CARRIERS_DIR.glob("*.json"))
    return [(name, fmt) for name in names for fmt in _formats(name)]
