# alquima-data-collector

Python = collect + process + CSV export + DB ingestion. Scoring/signals live in Express.

## Run (Ubuntu)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put FRED_API_KEY in .env
python -m alquima.features.f3_dashboard.macro.run --sink csv
```

Options: `--part all|market|indicators`, `--sink csv|db|both` (db comes in the next step).

Output goes to `output/`: `indicators.csv`, `market.csv`, `collector.log`, `ff_cache.json`.

`legacy/collector.py` is the old single-file version, kept only for reference.
