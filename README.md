# CGC moisture meter conversion tables

Machine-readable [Canadian Grain Commission](https://www.grainscanada.gc.ca/en/grain-quality/grain-grading/grading-factors/moisture-content/moisture-meter-conversion-tables.html) Model 919/3.5" moisture conversion tables.

Source PDFs remain on the CGC website. This repo republishes the grids as JSON for offline use.

## Layout

- `tables/manifest.json` — grain id, sample weight, table date/number, JSON filename
- `tables/<id>.json` — meter reading × temperature (°C 11–30) moisture grid
- `scripts/update_tables.py` — scrape the CGC index, download new PDFs, parse, publish

Load these files from:

`https://raw.githubusercontent.com/nightathemuseum/CGC-moisture-meter-tables/main/tables/manifest.json`

## Update schedule

GitHub Actions runs at the end of January, April, July, and October (CGC tables usually change in July), and can be run manually.

```
python scripts/update_tables.py
python scripts/update_tables.py --force
```

## JSON shape

```json
{
  "id": "cwrs",
  "grainType": "Wheat, Canada Western Red Spring, 66 kg/hL and over",
  "sampleG": 250,
  "tableDate": "2021-07",
  "tableNo": "12",
  "sourcePdf": "https://www.grainscanada.gc.ca/.../cwrs.pdf",
  "meterReadings": [5.0, 5.5],
  "temperaturesC": [11, 12, 13],
  "values": [[12.1, 12.0, 11.9], [12.2, 12.1, 12.0]]
}
```

`values[i][j]` is percent moisture at `meterReadings[i]` and `temperaturesC[j]`.

## Licence

Table data is produced by the Canadian Grain Commission. Reproduction here is for public agricultural use; see the [CGC website](https://www.grainscanada.gc.ca/) and the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).
