# Shopify CSV Uploader

A minimal FastAPI web app that converts a TRC "Juno Master Sheet" CSV into a Shopify Product Import CSV, using the Shopify export template for column order. The app also produces a research log for each SKU.

## Features
- `/enrich` endpoint accepts the master sheet and a Shopify export template.
- Generates `shopify_products.csv` ready for Products → Import and `research_log.csv` with lookup metadata.
- UI single page for uploading/downloading a ZIP containing both CSVs.
- Juno API client with environment-driven configuration and offline-safe fallback metadata.

## Setup
1. Install Python 3.11+ and create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
   python -m pip install --upgrade pip
   ```
2. Install dependencies from `requirements.txt` with the activated venv:
   ```bash
   pip install -r requirements.txt
   ```
   If `pip` is not found, install it with `python -m ensurepip --upgrade` (bundled with Python 3) and rerun the command.
3. Copy `.env.example` to `.env` and set optional Juno API credentials:
   ```bash
   cp .env.example .env
   # Set JUNO_API_BASE and JUNO_API_KEY if you have live access
   ```
4. (Optional) Place your Shopify template export in the repo root as `shopify-sample-products_export.csv` if you want a reusable local copy. The UI will still prompt for uploads when the file is absent.

## Running the app
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` to use the UI.

## Usage
1. Export a Shopify template CSV from your store (Products → Export) and save it.
2. Prepare the Juno Master Sheet CSV with columns:
   - `juno_cat`
   - `price_inr`
   - `tier`
   - `condition`
   - `inventory_qty` (defaults to 1 if blank)
   - Optional: `ean`, `format_override`, `edition_notes`
3. Upload both files in the UI and download the generated ZIP containing:
   - `shopify_products.csv` (mirrors template columns/order)
   - `research_log.csv` (source, confidence, flags per SKU)

## Notes
- Only the front image is used; description text is generated from metadata (genre/style/era and tracklist) and does not reuse review prose.
- The Juno client will call a live API if `JUNO_API_BASE` is set, otherwise a deterministic fallback is used for offline runs.
