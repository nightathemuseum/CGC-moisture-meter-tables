#!/usr/bin/env python3
"""Scrape CGC moisture conversion tables, parse PDFs, write JSON + manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pdfplumber
from bs4 import BeautifulSoup

INDEX_URL = (
    "https://www.grainscanada.gc.ca/en/grain-quality/grain-grading/"
    "grading-factors/moisture-content/moisture-meter-conversion-tables.html"
)
USER_AGENT = (
    "CGC-moisture-meter-tables/1.0 "
    "(+https://github.com/nightathemuseum/CGC-moisture-meter-tables)"
)
SKIP_STEMS = {"corntestwt", "peabeans2", "darkredkidney2", "lightredkidney1"}
STEM_TO_ID = {
    "barley": "barley",
    "hullbarley": "barley_hulless",
    "barleylightwt": "barley_lw",
    "azuki": "beans_azuki",
    "bb": "beans_black",
    "cranberry": "beans_cranberry",
    "darkredkidney": "beans_dark_red_kidney",
    "whitekidney": "beans_eastern_white_kidney",
    "beans-greatnorthern": "beans_great_northern",
    "lightredkidney": "beans_light_red_kidney",
    "otebo": "beans_otebo",
    "peabeans": "beans_pea",
    "pinb": "beans_pinto",
    "smallredbeans": "beans_small_red",
    "buckwheat": "buckwheat",
    "canary": "canary",
    "canola": "canola",
    "chickpeas": "chickpeas",
    "cornhighmoist": "corn_high",
    "cornlowmoist": "corn_low",
    "fababeans": "faba",
    "flax": "flax",
    "lentils-other": "lentils",
    "lentils-red": "lentils_red",
    "bmust": "mustard_b",
    "omust": "mustard_o",
    "ymust": "mustard_y",
    "oats": "oats",
    "ho-agn": "oats_hulless",
    "oatslightwttemp": "oats_lw",
    "peas": "peas",
    "rye": "rye",
    "safflower": "safflower",
    "soybean": "soybean",
    "splitpeas": "split_peas",
    "sunflower": "sunflower",
    "triticale": "triticale",
    "easthardred": "cehrw",
    "eastredspring": "cers",
    "cesrw": "cesrw",
    "ewww": "ceww",
    "wheat-cnhr": "cnhr",
    "cdaprairiespring": "cps",
    "amberdur": "cwad",
    "extrastrongredsp": "cwes",
    "hws": "cwhws",
    "cwrs": "cwrs",
    "redspringlightwt": "cwrs_lw",
    "swsw": "cwsws",
    "westernwinter": "cwrw",
    "hemp": "hemp",
    "solin": "solin",
}
DATA_ROW = re.compile(
    r"^\s*(\d+\.\d+)\s+((?:\d+\.\d+\s+){19}\d+\.\d+)\s+(\d+\.\d+)\s*$"
)
FOOTER_RE = re.compile(
    r"TABLE\s+NO\.?\s*([A-Z0-9]+)\s*[,•]\s*([A-ZÉÈÛ]+)\s+(\d{4})",
    re.IGNORECASE,
)
MONTHS = {
    "JANUARY": "01",
    "FEBRUARY": "02",
    "MARCH": "03",
    "APRIL": "04",
    "MAY": "05",
    "JUNE": "06",
    "JULY": "07",
    "AUGUST": "08",
    "SEPTEMBER": "09",
    "OCTOBER": "10",
    "NOVEMBER": "11",
    "DECEMBER": "12",
    "JANVIER": "01",
    "FEVRIER": "02",
    "FÉVRIER": "02",
    "MARS": "03",
    "AVRIL": "04",
    "MAI": "05",
    "JUIN": "06",
    "JUILLET": "07",
    "AOUT": "08",
    "AOÛT": "08",
    "SEPTEMBRE": "09",
    "OCTOBRE": "10",
    "NOVEMBRE": "11",
    "DECEMBRE": "12",
    "DÉCEMBRE": "12",
}
DEFAULT_TEMPS = list(range(11, 31))


def http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def stem_id(stem: str) -> str:
    key = stem.lower()
    if key in STEM_TO_ID:
        return STEM_TO_ID[key]
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")


def parse_html_date(raw: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", raw).strip()
    m = re.match(r"(.+),\s*(\S+)\s*$", text)
    if not m:
        return text, ""
    return m.group(1).rstrip("."), m.group(2)


def parse_footer(text: str) -> tuple[str | None, str | None]:
    m = FOOTER_RE.search(text)
    if not m:
        return None, None
    number, month, year = m.group(1), m.group(2).upper(), m.group(3)
    month_key = month.replace("É", "E").replace("Û", "U")
    mm = MONTHS.get(month) or MONTHS.get(month_key)
    date = f"{year}-{mm}" if mm else f"{year}-{month}"
    return number, date


def parse_pdf(path: Path) -> dict:
    rows: dict[float, list[float]] = {}
    footer_text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "TABLE NO" in text.upper() and not footer_text:
                for line in text.splitlines():
                    if line.upper().strip().startswith("TABLE NO"):
                        footer_text = line.strip()
                        break
            for line in text.splitlines():
                m = DATA_ROW.match(line.strip())
                if not m:
                    continue
                reading = float(m.group(1))
                tail = float(m.group(3))
                if abs(reading - tail) > 0.05:
                    continue
                values = [float(x) for x in m.group(2).split()]
                if len(values) != 20:
                    continue
                rows.setdefault(reading, values)
    if len(rows) < 10:
        raise ValueError(f"too few data rows in {path.name}: {len(rows)}")
    readings = sorted(rows)
    gaps = [b - a for a, b in zip(readings, readings[1:])]
    if gaps and min(gaps) <= 0:
        raise ValueError(f"non-monotonic meter readings in {path.name}")
    table_no, pdf_date = parse_footer(footer_text)
    return {
        "meterReadings": readings,
        "temperaturesC": DEFAULT_TEMPS,
        "values": [rows[r] for r in readings],
        "pdfTableNo": table_no,
        "pdfTableDate": pdf_date,
        "pdfFooter": footer_text,
    }


def scrape(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    entries: list[dict] = []
    section = soup.select_one("#tables")
    if section is None:
        raise ValueError("could not find #tables on CGC index page")
    for tr in section.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a = tds[0].find("a")
        if a is None or not a.get("href"):
            continue
        href = urljoin(base_url, a["href"])
        stem = Path(urlparse(href).path).stem
        if stem.lower() in SKIP_STEMS:
            continue
        label = re.sub(r"\s*\(PDF,.*?\)\s*$", "", a.get_text(" ", strip=True), flags=re.I)
        grams = re.search(r"\d+", tds[1].get_text())
        table_date, table_no = parse_html_date(tds[2].get_text(" ", strip=True))
        entries.append(
            {
                "id": stem_id(stem),
                "pdfStem": stem,
                "label": label,
                "sampleG": int(grams.group()) if grams else None,
                "tableDate": table_date,
                "tableNo": table_no,
                "sourcePdf": href,
            }
        )
    notables = soup.select_one("#notables")
    if notables is not None:
        for li in notables.select("li"):
            a = li.find("a")
            if a is None or not a.get("href"):
                continue
            href = urljoin(base_url, a["href"])
            stem = Path(urlparse(href).path).stem
            if stem.lower() in SKIP_STEMS:
                continue
            text = li.get_text(" ", strip=True)
            label = re.sub(r"\s*\(PDF,.*?\)\s*:?", "", a.get_text(" ", strip=True), flags=re.I)
            grams = re.search(r"(\d+)\s*gram", text, re.I)
            month = re.search(
                r"(January|February|March|April|May|June|July|August|"
                r"September|October|November|December)\s+(\d{4})",
                text,
                re.I,
            )
            table_date = ""
            if month:
                table_date = f"{month.group(2)}-{MONTHS[month.group(1).upper()]}"
            entries.append(
                {
                    "id": stem_id(stem),
                    "pdfStem": stem,
                    "label": label.strip(" :"),
                    "sampleG": int(grams.group(1)) if grams else None,
                    "tableDate": table_date,
                    "tableNo": "",
                    "sourcePdf": href,
                }
            )
    seen: set[str] = set()
    unique = []
    for e in entries:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        unique.append(e)
    return unique


def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {t["id"]: t for t in data.get("tables", [])}


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def needs_update(entry: dict, previous: dict | None, out_file: Path, force: bool) -> bool:
    if force or previous is None or not out_file.exists():
        return True
    return (
        previous.get("tableDate") != entry["tableDate"]
        or previous.get("tableNo") != entry["tableNo"]
        or previous.get("sourcePdf") != entry["sourcePdf"]
    )


def build_table_json(entry: dict, parsed: dict) -> dict:
    return {
        "id": entry["id"],
        "grainType": entry["label"],
        "sampleG": entry["sampleG"],
        "tableDate": entry["tableDate"],
        "tableNo": entry["tableNo"],
        "sourcePdf": entry["sourcePdf"],
        "meterReadings": parsed["meterReadings"],
        "temperaturesC": parsed["temperaturesC"],
        "values": parsed["values"],
    }


def run(out_dir: Path, cache_dir: Path, force: bool, android_assets: Path | None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    previous = load_manifest(manifest_path)

    html = http_get(INDEX_URL).decode("utf-8", errors="replace")
    entries = scrape(html, INDEX_URL)
    if not entries:
        raise SystemExit("no grain entries found on CGC index")

    errors: list[str] = []
    published: list[dict] = []
    updated = 0
    skipped = 0

    for i, entry in enumerate(entries):
        file_name = f"{entry['id']}.json"
        out_file = out_dir / file_name
        prev = previous.get(entry["id"])
        if not needs_update(entry, prev, out_file, force):
            published.append({**entry, "file": file_name, "status": "unchanged"})
            skipped += 1
            continue
        pdf_path = cache_dir / f"{entry['pdfStem']}.pdf"
        try:
            print(f"[{i + 1}/{len(entries)}] {entry['id']} {entry['sourcePdf']}", flush=True)
            pdf_path.write_bytes(http_get(entry["sourcePdf"]))
            time.sleep(0.35)
            parsed = parse_pdf(pdf_path)
            html_no = (entry.get("tableNo") or "").upper()
            pdf_no = (parsed.get("pdfTableNo") or "").upper()
            if html_no and pdf_no and html_no != pdf_no:
                print(f"  warn: table number HTML={entry['tableNo']} PDF={parsed['pdfTableNo']}", flush=True)
            table = build_table_json(entry, parsed)
            write_json(out_file, table)
            published.append(
                {
                    **entry,
                    "file": file_name,
                    "status": "updated",
                    "readings": len(parsed["meterReadings"]),
                    "pdfFooter": parsed["pdfFooter"],
                }
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"{entry['id']}: {exc}"
            errors.append(msg)
            print(f"  error: {msg}", flush=True)
            if out_file.exists() and prev:
                published.append({**prev, "file": file_name, "status": "kept_previous"})
            time.sleep(0.35)

    manifest = {
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": INDEX_URL,
        "tables": [
            {
                "id": p["id"],
                "label": p["label"],
                "sampleG": p.get("sampleG"),
                "tableDate": p.get("tableDate", ""),
                "tableNo": p.get("tableNo", ""),
                "file": p["file"],
                "sourcePdf": p.get("sourcePdf", ""),
            }
            for p in published
        ],
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"updated={updated} unchanged={skipped} errors={len(errors)} total={len(published)}")

    if android_assets is not None:
        android_assets.mkdir(parents=True, exist_ok=True)
        copied = 0
        for p in published:
            src = out_dir / p["file"]
            if src.exists():
                (android_assets / p["file"]).write_bytes(src.read_bytes())
                copied += 1
        print(f"copied {copied} files to {android_assets}")

    if errors:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--out", type=Path, default=root / "tables")
    parser.add_argument("--cache", type=Path, default=root / "pdfs")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--android-assets", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        return run(args.out, args.cache, args.force, args.android_assets)
    except urllib.error.URLError as exc:
        print(f"network error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
