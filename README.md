```markdown
# Random Movie Recommender

[Read in Chinese](./README.zh.md)

A web application based on Flask that fetches movie data from TMDb API for random recommendations, supporting caching, favorites, and genre filtering. Suitable for learning API calls, recommendation algorithms, and web development.

## Features
- Random movie recommendations (single or batch, with genre filtering)
- Display movie details (title, year, rating, genres, overview)
- Local caching to reduce API requests
- Web interface: dropdown for genre selection, recommendation buttons, favorites management
- Persistent favorites (stored in data/favorites.json)

## Requirements
- Python 3.8+
- Flask
- requests

## Installation
Run in the project root directory (recommended to use venv):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt    # If no requirements.txt, run pip install flask requests
```

## Configure API Key
The program uses TMDb API. After obtaining the key, set the environment variable:

### Get TMDB API Key:
Visit [TMDB website](https://www.themoviedb.org/), sign up and generate an API key (v3 auth key).

### Set environment variable in terminal and run:
1. Stop the current app (Ctrl+C).
2. In PowerShell:
   ```
   $env:TMDB_API_KEY = "YOUR_API_KEY_HERE"
   python app.py
   ```
3. Or in CMD:
   ```
   set TMDB_API_KEY=YOUR_API_KEY_HERE
   python app.py
   ```
4. Replace `YOUR_API_KEY_HERE` with your actual key.

### Verification:
- After restart, visit http://localhost:5000.
- Check if warnings persist in terminal. If issues remain, confirm the key is correct, and try refreshing the page or clicking the "🔄 Refresh Data" button.
- For permanent setup (no need to enter each time), add `TMDB_API_KEY` to Windows system environment variables. If problems persist, provide more terminal output.

> Prefer environment variables to avoid committing secrets to the repository.

## Run
Execute directly in the activated virtual environment:
```powershell
python app.py
```
Then open http://localhost:5000 in your browser to use the web interface.

## Tests
The project includes pytest test cases (tests/). Run:
```powershell
pip install pytest
python -m pytest -q
```

## Project Structure
```
Random Movie Recommender/
├─ data/                      # Cache data and favorites (favorites.json)
├─ src/
│  ├─ api_client.py          # TMDb API client
│  ├─ requester.py           # Request wrapper
│  ├─ endpoints.py           # API endpoint handling
│  ├─ factory.py             # Client factory
│  ├─ storage.py             # Data storage and caching
│  ├─ recommenders.py        # Recommendation algorithms
│  ├─ utils.py               # Utility functions (formatting, filtering, etc.)
│  ├─ preferences.py         # User preference settings
│  ├─ retry_policy.py        # Retry policy
├─ tests/                     # Unit tests
│  ├─ test_api.py
│  ├─ test_endpoints.py
│  ├─ test_factory.py
│  ├─ test_recommenders.py
│  ├─ test_storage.py
│  ├─ test_utils.py
│  └─ conftest.py
├─ app.py                     # Flask backend application
├─ index.html                 # Web frontend interface
├─ config.py (optional)       # Configuration (optional)
└─ README.md
```

## Troubleshooting
- No options in dropdown: Ensure TMDB_API_KEY is set correctly, check for 500 errors in terminal.
- Repeated recommendations: Check caching strategy, ensure random pages and query parameters are handled properly.
- API request failures: Confirm network/proxy and TMDB_API_KEY are correct.

## Contributing
Welcome to submit issues or PRs. Please explain the purpose of changes in PRs and include unit tests if applicable.

## License
MIT
