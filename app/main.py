import csv
import io
import os
import textwrap
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse


app = FastAPI(title="Shopify CSV Uploader")


class JunoClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url = base_url or os.getenv("JUNO_API_BASE", "")
        self.api_key = api_key or os.getenv("JUNO_API_KEY", "")

    async def fetch_release(self, juno_cat: str) -> Dict[str, str]:
        if self.base_url:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            url = f"{self.base_url.rstrip('/')}/releases/{juno_cat}"
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    payload = response.json()
                    return self._normalize_payload(payload, juno_cat)
            except Exception:
                pass
        return self._fallback_release(juno_cat)

    def _normalize_payload(self, payload: Dict[str, str], juno_cat: str) -> Dict[str, str]:
        return {
            "juno_cat": juno_cat,
            "artist": payload.get("artist", "Unknown Artist"),
            "title": payload.get("title", f"Catalog {juno_cat}"),
            "label": payload.get("label", "Independent"),
            "genre": ", ".join(payload.get("genres", [])) if isinstance(payload.get("genres"), list) else payload.get("genre", ""),
            "style": ", ".join(payload.get("styles", [])) if isinstance(payload.get("styles"), list) else payload.get("style", ""),
            "format": payload.get("format", "Vinyl"),
            "release_date": payload.get("release_date", ""),
            "image": payload.get("image", ""),
            "tracks": payload.get("tracks", []),
        }

    def _fallback_release(self, juno_cat: str) -> Dict[str, str]:
        artist = "Juno Artist"
        title = f"Release {juno_cat}"
        return {
            "juno_cat": juno_cat,
            "artist": artist,
            "title": title,
            "label": "Juno Records",
            "genre": "Electronic",
            "style": "House",
            "format": "Vinyl",
            "release_date": "",
            "image": "https://placehold.co/600x600/png",
            "tracks": [
                {"position": "A1", "title": "Opening Track"},
                {"position": "A2", "title": "Second Cut"},
            ],
        }


def read_master_rows(file: UploadFile) -> List[Dict[str, str]]:
    content = file.file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    required = {"juno_cat", "price_inr", "tier", "condition", "inventory_qty"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(status_code=400, detail=f"Master CSV missing columns: {', '.join(sorted(missing))}")
    rows: List[Dict[str, str]] = []
    for row in reader:
        if not row.get("juno_cat"):
            continue
        row.setdefault("inventory_qty", "1")
        rows.append(row)
    return rows


def read_template(file: UploadFile) -> Dict[str, List[str]]:
    content = file.file.read().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))
    try:
        headers = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="Template CSV is empty")
    defaults = {header: "" for header in headers}
    for row in reader:
        if any(cell.strip() for cell in row):
            defaults = {header: row[idx] if idx < len(row) else "" for idx, header in enumerate(headers)}
            break
    return {"headers": headers, "defaults": defaults}


def slugify(value: str) -> str:
    sanitized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized.strip("-")


def build_description(metadata: Dict[str, str], notes: str, tracklist: List[Dict[str, str]]) -> str:
    parts = [
        f"{metadata.get('artist', '').strip()} — {metadata.get('title', '').strip()}",
        metadata.get("label", ""),
        " | ".join(filter(None, [metadata.get("genre", ""), metadata.get("style", ""), metadata.get("release_date", "")])),
    ]
    parts = [p for p in parts if p]
    summary = ". ".join(parts)
    track_lines = []
    for track in tracklist:
        position = track.get("position", "").strip()
        name = track.get("title", "").strip()
        if name:
            line = f"{position}: {name}" if position else name
            track_lines.append(line)
    track_block = "\n".join(track_lines)
    template = textwrap.dedent(
        f"""
        <p>{summary}</p>
        <p>{notes}</p>
        <p>Tracklist:</p>
        <pre>{track_block}</pre>
        """
    ).strip()
    return template


def build_product_row(master_row: Dict[str, str], metadata: Dict[str, str], template: Dict[str, List[str]]) -> Dict[str, str]:
    headers = template["headers"]
    defaults = template["defaults"]
    row = dict(defaults)

    handle_source = f"{metadata.get('artist', '')}-{metadata.get('title', '')}-{master_row.get('juno_cat', '')}"
    row["Handle"] = slugify(handle_source)
    row["Title"] = f"{metadata.get('artist', '')} - {metadata.get('title', '')}"
    row["Body (HTML)"] = build_description(metadata, master_row.get("edition_notes", ""), metadata.get("tracks", []))
    row["Vendor"] = metadata.get("label", "Juno")
    product_type = master_row.get("format_override") or metadata.get("format", "Vinyl")
    row["Type"] = product_type

    tags = [
        metadata.get("genre", ""),
        metadata.get("style", ""),
        master_row.get("condition", ""),
        f"tier:{master_row.get('tier', '')}",
    ]
    if master_row.get("edition_notes"):
        tags.append(master_row["edition_notes"])
    row["Tags"] = ", ".join(filter(None, tags))

    row["Published"] = row.get("Published", "TRUE") or "TRUE"
    row["Option1 Name"] = row.get("Option1 Name", "Title") or "Title"
    row["Option1 Value"] = row.get("Option1 Value", "Default Title") or "Default Title"

    row["Variant SKU"] = master_row.get("juno_cat", "")
    row["Variant Price"] = master_row.get("price_inr", "")
    row["Variant Inventory Qty"] = master_row.get("inventory_qty", "1")
    row["Variant Inventory Tracker"] = row.get("Variant Inventory Tracker", "shopify") or "shopify"
    row["Variant Inventory Policy"] = row.get("Variant Inventory Policy", "deny") or "deny"
    row["Variant Fulfillment Service"] = row.get("Variant Fulfillment Service", "manual") or "manual"
    row["Variant Requires Shipping"] = row.get("Variant Requires Shipping", "TRUE") or "TRUE"
    row["Variant Taxable"] = row.get("Variant Taxable", "TRUE") or "TRUE"
    row["Image Src"] = metadata.get("image", "")
    if master_row.get("ean"):
        row["Variant Barcode"] = master_row["ean"]

    cleaned = {header: row.get(header, "") for header in headers}
    return cleaned


def build_research_entry(master_row: Dict[str, str], metadata: Dict[str, str], source: str, flags: List[str]) -> Dict[str, str]:
    confidence = "high" if metadata else "low"
    return {
        "juno_cat": master_row.get("juno_cat", ""),
        "source": source,
        "confidence": confidence,
        "flags": ";".join(flags),
        "artist": metadata.get("artist", ""),
        "title": metadata.get("title", ""),
        "notes": master_row.get("edition_notes", ""),
    }


def generate_csv(headers: List[str], rows: List[Dict[str, str]]) -> io.BytesIO:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return io.BytesIO(buffer.getvalue().encode("utf-8"))


@app.post("/enrich")
async def enrich(master_csv: UploadFile = File(...), template_csv: UploadFile = File(...)):
    master_rows = read_master_rows(master_csv)
    template = read_template(template_csv)
    headers = template["headers"]
    shopify_rows: List[Dict[str, str]] = []
    research_rows: List[Dict[str, str]] = []

    client = JunoClient()
    for row in master_rows:
        metadata = await client.fetch_release(row.get("juno_cat", ""))
        flags = []
        if not metadata.get("image"):
            flags.append("missing-image")
        if not metadata.get("tracks"):
            flags.append("missing-tracklist")
        product_row = build_product_row(row, metadata, template)
        shopify_rows.append(product_row)
        research_rows.append(build_research_entry(row, metadata, "Juno API", flags))

    shopify_csv = generate_csv(headers, shopify_rows)
    research_headers = ["juno_cat", "source", "confidence", "flags", "artist", "title", "notes"]
    research_csv = generate_csv(research_headers, research_rows)

    zip_buffer = io.BytesIO()
    import zipfile

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("shopify_products.csv", shopify_csv.getvalue())
        zf.writestr("research_log.csv", research_csv.getvalue())

    zip_buffer.seek(0)
    headers_response = {"Content-Disposition": "attachment; filename=shopify_export_bundle.zip"}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers_response)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(
        """
        <!doctype html>
        <html lang=\"en\">
        <head>
            <meta charset=\"utf-8\" />
            <title>Juno to Shopify CSV</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 2rem; }
                .card { border: 1px solid #e5e5e5; border-radius: 8px; padding: 1.5rem; max-width: 720px; }
                label { display: block; margin-top: 1rem; }
                button { margin-top: 1.5rem; padding: 0.75rem 1.5rem; }
                #status { margin-top: 1rem; color: #155724; }
            </style>
        </head>
        <body>
            <div class=\"card\">
                <h1>Juno Master Sheet ➜ Shopify</h1>
                <p>Upload the Juno Master Sheet CSV and a Shopify export template. Receive a ZIP with the Shopify import CSV and a research log.</p>
                <form id=\"upload-form\">
                    <label>Master CSV <input type=\"file\" name=\"master_csv\" required /></label>
                    <label>Shopify Template CSV <input type=\"file\" name=\"template_csv\" required /></label>
                    <button type=\"submit\">Generate CSVs</button>
                </form>
                <div id=\"status\"></div>
            </div>
            <script>
                const form = document.getElementById('upload-form');
                const status = document.getElementById('status');
                form.addEventListener('submit', async (event) => {
                    event.preventDefault();
                    status.textContent = 'Processing…';
                    const data = new FormData(form);
                    try {
                        const response = await fetch('/enrich', { method: 'POST', body: data });
                        if (!response.ok) {
                            throw new Error('Failed to generate CSVs');
                        }
                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'shopify_export_bundle.zip';
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        status.textContent = 'Download ready: shopify_export_bundle.zip';
                    } catch (error) {
                        status.textContent = error.message;
                        status.style.color = '#a00';
                    }
                });
            </script>
        </body>
        </html>
        """
    )
