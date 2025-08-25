# Random Movie Recommender

[阅读中文版本](./README.zh.md)

A small CLI tool that picks random movies from TMDb and shows basic info with emojis for readability. Good for learning API usage, JSON handling and simple recommendation logic.

## Features
- Single or batch random recommendations
- Shows title, year, rating, genres and short overview (emoji-enhanced)
- Optional local caching to reduce API calls
- Simple, testable codebase

## Requirements
- Python 3.8+
- requests

## Install (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # or: pip install requests
```

## Configure TMDb API Key
Preferred: set environment variable
```powershell
$env:TMDB_API_KEY = "your_api_key_here"
```

Or create a local `config.py` with:
```python
def get_tmdb_key():
    return "your_api_key_here"
```

The code prefers the environment variable to avoid committing secrets.

## Run
```powershell
python main.py
```

### Interactive keys
- Enter: recommend one movie  
- b: batch recommend (3 movies)  
- r: refresh (re-fetch from API)  
- q: quit

## Tests (pytest)
```powershell
pip install pytest
python -m pytest -q
```

## Project layout (summary)
```
Random Movie Recommender/
├─ data/                      # cache files
├─ src/
│  ├─ api_client.py
│  ├─ requester.py
│  ├─ endpoints.py
│  ├─ factory.py
│  ├─ storage.py
│  ├─ recommenders.py
│  └─ utils.py
├─ main.py
├─ config.py (optional)
└─ README.en.md
```

## Troubleshooting
- Many same-year results after refresh: check pagination/random-page selection and caching keys include page/query.  
- API errors: verify `TMDB_API_KEY` and network/proxy settings.

## Planned improvements (short-term priorities)

The project roadmap prioritizes usability, reliability and user features. The next planned items are:

1. Genre filter & fuzzy matching (priority: High)
   - Allow users to request recommendations filtered by genre (English/Chinese).
   - Use TMDb /genre/movie/list for name→id mapping; fallback to fuzzy matching on movie.genres, genre_ids, title or overview.
   - CLI/interactive: initial prompt and `g` command to set/clear genre.
   - Acceptance: setting a known genre returns only matching movies; unknown genre falls back with notice.

2. Tests and CI (priority: High)
   - Add unit tests for core modules (storage, recommenders, utils, genre filtering).
   - Use request mocking (responses / requests-mock) to simulate TMDb.
   - Add GitHub Actions workflow to run pytest on push/PR.
   - Acceptance: tests run in CI; core logic covered by unit tests.

3. Better cache (per-query caching) (priority: Medium)
   - Cache results per query hash (include query params & page) instead of a single global cache file.
   - Keep TTL, support manual cache clear and forced refresh (`r`).
   - Acceptance: different queries use separate cache files; forced refresh bypasses cache.

4. Favorites (persisted user prefs) (priority: Medium)
   - Allow users to save favorites locally (data/favorites.json), list and remove favorites.
   - Interactive commands: `f` to save current, `fav-list`, `fav-remove`.
   - Acceptance: favorites persisted, import/export as JSON supported.

## Contributing
PRs and issues welcome. Please include tests for behavior changes.

## License
MIT