"""Build one current Maps reference from independently captured, pinned sources.

This is an explicit custom reference update for d1ac only. It never takes an
Actor workbook as input and does not change the official comparison function.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from repair_pdf_reference import read, sha, write_new

TASK_ID = "d1acdb87-bb67-4f30-84aa-990e56a09c92"
UPSTREAM_COMMIT = "5123bfdbbc34b947bcffcff564abc62d0ab7072d"
TASK_SHA256 = "993658835ec96d628ad6e47ed015c7ed4fd6af186086407662e9286ecaa541d9"
ORIGINAL_GOLD_SHA256 = "fd60eecfc60cac1be90b81aa83c5a3322f321e39ac1e516bc023d967195bdd54"
ACTUAL_SHA256 = "0cf39e485a7a2e975775dfd0710609a6feac1358ad6906a59c392ad632ac72f4"
KIND = "task-scoped-current-google-maps-reference-v1"
HEADERS = ("Restaurant Name", "Address", "Contact Number", "Website")
# Approved independent anonymous local-browser captures. No Actor data was used.
SOURCES = (
    ("MingPavilion", "Ming Pavilion", "Ming Pavilion", "89c2604a4736dfd17cb03166cf30bab03c40f0f09a56501b1e72b6d1cd2846e3", "e749723756f5af091215a1e058e245db839796c58cc0a570646561e01ec0e3cb"),
    ("CristalRoom", "Cristal Room by Anne-Sophie Pic", "Cristal Room by Anne-Sophie Pic", "693bdb1cff6ad070a86cdb9c7d7f4c87db72b4cb2edd35f8d2328476a3022a93", "af327be4920f0d42081b7ee2012682f9fd0b29b503508b534dbe976eb8079ef5"),
    ("Leela", "Leela", "Leela", "bd7ee8a8211fd38a946cc3aadfaf45feb67f25fcbfbd201430d50c7cf33a74c8", "442ebdda3edff8a9c1b36948353b9ff800457ef6bbae879b9f6e917e174340b7"),
    ("Nobu", "Nobu", "NOBU Hong Kong - Japanese Restaurant", "51873cea131e5ebd1dc21db7d344f51c147d02b63aed032556d560d28a32562d", "11d55f75676c116444333ce64415de1635bae8aa0d6ef1fef318912bd9cbfad6"),
    ("Niras", "Niras", "NIRAS (K11 MUSEA)", "052deff798faee9fcd9bee43b4cf419a715d5f3730f831b212716ead2f0d7520", "1c1e857b573915682e83d1e6b952ea451d5f9218787d29795be2651926f46c5c"),
)
ORIGINAL_OPTIONS = {"rules": [{"type": "sheet_fuzzy", "sheet_idx0": "RNSheet1", "sheet_idx1": "ENSheet1", "rules": [
    {"range": ["A1:A6"], "type": "exact_match"},
    {"range": ["B1:B6"], "type": "exact_match", "ignore_case": True, "ignore_chars": " ,/-", "preserve_numeric_tokens": True,
     "normalization_regex": [[r"(?<=\d)\s*[‐‑‒–—−]\s*(?=\d)", "-"], [r"(?i)\bRd\b\.?", "Road"], [r"(?i)\bSt\b\.?", "Street"]]},
    {"range": ["C1:C6"], "type": "phone_match", "allow_missing_expected": True},
    {"range": ["D1:D6"], "type": "domain_match"}]}]}


def repair_options(options):
    """Preserve strict address/number rules; allow only this known missing D6."""
    if options != ORIGINAL_OPTIONS:
        raise ValueError("Original task-scoped table options changed")
    value = deepcopy(options)
    rules = value["rules"][0]["rules"]
    rules[3]["range"] = ["D1:D5"]
    rules.append({"range": ["D6"], "type": "exact_match"})
    return value


def source_records(snapshot_dir, require_screenshots=False):
    records = []
    for row, (stem, original_name, observed_name, checksum, png_sha) in enumerate(SOURCES, 2):
        path = Path(snapshot_dir) / (stem + ".json")
        if sha(path) != checksum:
            raise ValueError("Independent Maps snapshot hash changed: " + stem)
        data = read(path)
        url = urlsplit(data.get("url", ""))
        if (data.get("name") != observed_name or data.get("observation_kind") != "independent_live_Google_Maps_DOM"
                or url.scheme != "https" or url.hostname != "www.google.com" or not url.path.startswith("/maps/")
                or not data.get("observed_at_utc") or not str(data.get("address", "")).startswith("Address: ")
                or not str(data.get("phone", "")).startswith("Phone: +852 ")):
            raise ValueError("Independent Maps source identity/fields changed")
        if row == 6:
            if (data.get("permanently_closed") is not True or data.get("website") is not None
                    or any(b.get("id") == "authority" for b in data.get("info_buttons", []))):
                raise ValueError("Missing Niras website needs the independently observed closed/null listing")
        elif data.get("permanently_closed") is not False or urlsplit(data.get("website", "")).scheme != "https":
            raise ValueError("Expected the independently observed available restaurant website")
        if require_screenshots and sha(Path(snapshot_dir) / (stem + ".png")) != png_sha:
            raise ValueError("Independent Maps screenshot hash changed: " + stem)
        records.append({"row": row, "input_restaurant_name": original_name, "observed_name": observed_name,
            "source_file": stem + ".json", "source_json_sha256": checksum, "screenshot_sha256": png_sha,
            "observed_at_utc": data["observed_at_utc"], "url": data["url"],
            "permanently_closed": data["permanently_closed"],
            "cells": {"B" + str(row): data["address"][len("Address: "):].strip(),
                      "C" + str(row): data["phone"][len("Phone: "):].strip(),
                      "D" + str(row): data["website"]}})
    return records


def _books(original_gold, reference=None):
    from openpyxl import load_workbook
    if sha(original_gold) != ORIGINAL_GOLD_SHA256:
        raise ValueError("Original Gold template differs from the audited preserved reference")
    original = load_workbook(original_gold)
    if original.sheetnames != ["Sheet1"]:
        raise ValueError("Original reference sheet identity changed")
    sheet = original["Sheet1"]
    if tuple(sheet.cell(1, n).value for n in range(1, 5)) != HEADERS or [sheet.cell(n, 1).value for n in range(2, 7)] != [s[1] for s in SOURCES]:
        raise ValueError("Original headers, restaurant identities or row order changed")
    return original, load_workbook(reference) if reference is not None else None


def build_reference(original_gold, snapshot_dir, output_dir):
    """Produce a distinct sealed artifact; original Gold and all inputs stay intact.

    Future prepare code may reuse this artifact and repair_options explicitly.
    There is deliberately no global getter/metric monkeypatch.
    """
    original_gold, output = Path(original_gold).resolve(), Path(output_dir).resolve()
    records = source_records(snapshot_dir, require_screenshots=True)
    original, _ = _books(original_gold)
    before = sha(original_gold)
    output.mkdir(parents=True, exist_ok=False)
    (output / "sources").mkdir()
    for record in records:
        shutil.copyfile(Path(snapshot_dir) / record["source_file"], output / "sources" / record["source_file"])
        for coordinate, value in record["cells"].items():
            cell = original["Sheet1"][coordinate]
            # A historical hyperlink repopulates an otherwise empty cell on
            # reload. The current source replaces the website, link included.
            if coordinate.startswith("D"):
                cell.hyperlink = value
            cell.value = value
    destination = output / "current-reference.xlsx"
    original.save(destination)
    provenance = {"schema_version": 1, "kind": KIND, "task_id": TASK_ID,
        "original_gold_sha256": before, "reference_sha256": sha(destination),
        "builder_sha256": sha(Path(__file__)), "source_records": records,
        "reference_source": "five independent current Google Maps DOM captures; not Actor output",
        "screenshots": "SHA-bound original local captures; images are not copied into this artifact",
        "preserved": "Original headers, A column, row order and other cells; B2:D6 exclusively from independent source records",
        "boundary": "Niras website:null means no current Maps authority link on the observed closed listing; it does not prove its historical domain is globally dead."}
    write_new(output / "provenance.json", provenance)
    if sha(original_gold) != before:
        raise ValueError("Original Gold changed during reference generation")
    verify_reference(original_gold, output)
    return provenance


def verify_reference(original_gold, output_dir):
    output = Path(output_dir).resolve()
    provenance = read(output / "provenance.json")
    records = source_records(output / "sources")
    reference = output / "current-reference.xlsx"
    if (provenance.get("kind") != KIND or provenance.get("task_id") != TASK_ID
            or provenance.get("original_gold_sha256") != sha(original_gold)
            or provenance.get("reference_sha256") != sha(reference)
            or provenance.get("builder_sha256") != sha(Path(__file__))
            or provenance.get("source_records") != records):
        raise ValueError("Reference artifact/provenance/source binding changed")
    original, current = _books(original_gold, reference)
    if original.sheetnames != current.sheetnames:
        raise ValueError("Reference sheets changed")
    changed = {coordinate: value for record in records for coordinate, value in record["cells"].items()}
    for old_sheet, new_sheet in zip(original, current):
        if (old_sheet.max_row, old_sheet.max_column) != (new_sheet.max_row, new_sheet.max_column):
            raise ValueError("Reference dimensions changed")
        for row in old_sheet:
            for old in row:
                new = new_sheet[old.coordinate]
                expected = changed.get(old.coordinate, old.value)
                # openpyxl materializes an all-zero style for newly populated
                # formerly empty cells; it is the same default formatting.
                if new.value != expected or tuple(old._style or [0] * 9) != tuple(new._style or [0] * 9):
                    raise ValueError("Reference cell/layout differs from the independent source: " + old.coordinate)
                old_link = old.hyperlink.target if old.hyperlink else None
                expected_link = changed[old.coordinate] if old.coordinate.startswith("D") and old.coordinate in changed else old_link
                if (new.hyperlink.target if new.hyperlink else None) != expected_link:
                    raise ValueError("Reference hyperlink differs from the independent source")
    return provenance
