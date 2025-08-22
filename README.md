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

## Contributing
PRs and issues welcome. Please include tests for behavior changes.

## License
MIT