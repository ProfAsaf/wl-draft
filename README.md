# W/L Draft 26–27

Live standings for a five-person NBA draft where each pick is a team's wins or its losses.

**Live at https://profasaf.github.io/wl-draft/**

- `site/` is the page GitHub Pages serves. It reads `site/data.json` and polls ESPN's scoreboard every 30 seconds while games are on.
- `scripts/update_data.py` refreshes `site/data.json` from ESPN. GitHub Actions runs it every 15 minutes during game hours (`.github/workflows/update.yml`) and commits the data only when something changed.
- `scripts/wl.py` holds the scoring and the title-odds model; `scripts/espn.py` reads ESPN.
- `data/` holds the draft, the preseason lines and team info, plus the season's games and the title-odds history the pipeline maintains.
- `mockup/` is the clickable design mockup with a sample season (`scripts/make_sample_data.py`).

Design notes are in [DESIGN.md](DESIGN.md).

## Run it locally

```bash
pip install -r requirements.txt
python scripts/update_data.py
python -m http.server 8766 --directory site
```

Then open http://localhost:8766.
