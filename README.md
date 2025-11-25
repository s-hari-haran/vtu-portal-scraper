## vtu-portal-scraper

Small project: a Python Selenium scraper for VTU InternYet internship listings.

Files included:

- `scrape_vtu_internships.py` — main scraper script (Selenium + webdriver-manager).
- `requirements.txt` — required Python packages.

Quick start

1. (Recommended) run locally in a virtualenv with Chrome installed.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrape_vtu_internships.py --headless
```

2. Optional args: `--url`, `--max-pages`, `--keyword`, `--json`, `--output`.

Note: The repository no longer contains a committed virtualenv. Add your own local `.venv` if needed.

If you want, I can:

- Add a requests+BeautifulSoup fallback (no browser required).
- Add detail-page scraping for each internship.
- Add CI or a small test harness.
