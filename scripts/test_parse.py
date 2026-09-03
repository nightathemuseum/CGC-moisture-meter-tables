#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_tables import parse_footer, parse_html_date, parse_pdf, scrape, stem_id


def test_ids():
    assert stem_id("cwrs") == "cwrs"
    assert stem_id("hullbarley") == "barley_hulless"
    assert stem_id("Triticale") == "triticale"
    assert stem_id("cdaprairiespring") == "cps"


def test_dates():
    assert parse_html_date("2022-07, 14") == ("2022-07", "14")
    assert parse_html_date("1979-rev., 10") == ("1979-rev", "10")
    assert parse_html_date("2000-07, 11A") == ("2000-07", "11A")
    no, date = parse_footer("TABLE NO. 14, JULY 2022 PAGE 2 OF 2")
    assert no == "14" and date == "2022-07"
    no, date = parse_footer("TABLE NO. 1 • AUGUST 1994 CALIBRATION : Two-stage")
    assert no == "1" and date == "1994-08"


def test_scrape_fixture():
    html = Path("/tmp/opencode/cgc-pdfs/tables.html")
    if not html.exists():
        return
    entries = scrape(html.read_text(), "https://www.grainscanada.gc.ca/en/grain-quality/grain-grading/grading-factors/moisture-content/moisture-meter-conversion-tables.html")
    ids = {e["id"] for e in entries}
    assert "barley" in ids
    assert "cwrs" in ids
    assert "hemp" in ids
    assert "corn_low" in ids
    assert "corntestwt" not in {e["pdfStem"].lower() for e in entries}


def test_pdfs():
    cache = Path("/tmp/opencode/cgc-pdfs")
    cases = {
        "barley.pdf": (95, 5.0, 52.0, 8.9),
        "canola.pdf": (150, 3.5, 78.0, 5.6),
        "peas.pdf": (130, 5.0, 69.5, 8.6),
        "hullbarley.pdf": (150, 5.0, 79.5, 8.7),
    }
    for name, (n, lo, hi, at20) in cases.items():
        path = cache / name
        if not path.exists():
            continue
        parsed = parse_pdf(path)
        assert len(parsed["meterReadings"]) == n, name
        assert parsed["meterReadings"][0] == lo
        assert parsed["meterReadings"][-1] == hi
        assert parsed["values"][0][9] == at20


if __name__ == "__main__":
    test_ids()
    test_dates()
    test_scrape_fixture()
    test_pdfs()
    print("ok")
