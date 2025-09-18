# Project Setup with uv

Use this guide to bootstrap the Streamlit + Dify demo with the [uv](https://docs.astral.sh/uv/) Python packaging tool.

## Requirements
- macOS, Linux, or Windows with shell access
- Python 3.11+ (uv can install/manage this for you)
- Dify API key with access to the workflow you want to call

## 1. Install uv
Choose the installer that matches your platform:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex
```

Reload your shell (or follow the on-screen instructions) so `uv` is on the PATH, then confirm:

```bash
uv --version
```

## 2. Clone or update the repo

```bash
git clone <your-fork-or-this-repo-url>
cd demo_dify
```

If you already have the repo locally, pull the latest changes and `cd` into it.

## 3. Create the project environment
`uv venv` creates the virtual environment up front so you can manually activate it (if desired) before syncing dependencies.

```bash
uv venv
```

This will place a `.venv` directory in the project root. Activate it if you prefer working in an activated shell:

```bash
source .venv/bin/activate      # macOS / Linux
.venv\\Scripts\\activate         # Windows PowerShell
```

## 4. Install dependencies with uv
`uv` understands the `pyproject.toml` + `uv.lock` files shipped with the repo. The sync command will:
- make sure you have a compatible Python interpreter (3.11 by default)
- install the exact dependency set recorded in `uv.lock` into `.venv`

```bash
uv sync
```

Whenever you change dependencies (see step 8), re-run `uv sync` to update the local environment.

> Tip: if you skip manual activation, the examples below use `uv run`, which automatically selects `.venv`.

## 5. Provide Dify credentials
The app expects the Dify API key and optional settings via Streamlit secrets or environment variables.

### Option A — `.streamlit/secrets.toml`
Copy the template and fill in your values:

```toml
# .streamlit/secrets.toml
DIFY_API_KEY = "your_api_key"
BASE_URL = "https://api.dify.ai"      # optional override
WORKFLOW_ID = ""                       # optional, required on some Dify versions
HTTP_TIMEOUT = 180                      # optional, seconds
```

### Option B — environment variables

```bash
export DIFY_API_KEY="your_api_key"
export BASE_URL="https://api.dify.ai"
export WORKFLOW_ID=""         # optional
export HTTP_TIMEOUT="180"      # optional
```

Set these before starting Streamlit (or add them to a `.env` file and load it via your shell).

## 6. Run the Streamlit app

```bash
uv run streamlit run app.py
```

`uv` will drop you into the environment, start Streamlit, and bind to the default port (`http://localhost:8501`). When prompted in the UI, supply the portfolio inputs and click **Generate HTML via Dify**.

To change the port or enable headless mode, append standard Streamlit flags, e.g. `uv run streamlit run app.py --server.port 8502`.

## 7. Run the extraction smoke test

```bash
uv run python test_extraction.py
```

The script validates the HTML extraction helper against the bundled `output.json` payload and prints a short success message.

## 8. Managing dependencies with uv
- Add a new runtime dependency: `uv add <package-name>`
- Add a development-only dependency: `uv add --dev <package-name>`
- Upgrade everything to the latest allowed versions: `uv lock --upgrade` followed by `uv sync`

`uv` keeps `pyproject.toml` and `uv.lock` in sync automatically. Commit both files whenever you change dependencies.

## 9. Troubleshooting
- **Missing interpreter**: run `uv python install 3.11` to download a managed Python build that satisfies `requires-python = ">=3.11"`.
- **Auth errors**: double-check `DIFY_API_KEY` in secrets or environment variables.
- **Slow responses / timeouts**: adjust `HTTP_TIMEOUT` in secrets or env vars.
- **Fresh start**: remove `.venv` and run `uv sync` again to recreate the environment.

You're now ready to iterate on the Dify workflow UI locally with reproducible dependency management via `uv`.
