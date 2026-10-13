# Sponsor prototype, Zotero retrieval, and CSV extraction

The sponsor's original extraction architecture is unchanged:

`PDFMinerLoader → RecursiveCharacterTextSplitter → LangChain/Ollama → Pydantic parser → pandas CSV`

The added downloader is a separate ingestion step. It does not call an LLM, parse article
text, select extraction results, or generate CSV files. Original prompts, schema, chunking,
result selection, and CSV columns remain in `PV-Work/mainScript/extraction.py`.

## Structured CSV extractor

`extract_csv.py` is a separate command for the downloaded corpus. It calls local
Ollama directly with an enforced JSON schema for the same 27 article fields and
an exact source quote for cell performance. It validates the object, checks the quote
and reported numbers against the excerpt, and retries failed/invalid responses once. It saves
one CSV row per processed PDF, including rows with no data or extraction errors.
The sponsor's original extractor is unchanged. The dashboard defaults to the new
structured worker; `--extractor original` selects the preserved observer instead.

From the repository root, with Ollama running:

```powershell
.\.venv\Scripts\python.exe -m pip install -r SponsorPrototype/requirements-extraction.txt
ollama pull gemma3:1b
# Try one paper first:
.\.venv\Scripts\python.exe SponsorPrototype/extract_csv.py --limit 1
# Process the entire downloaded corpus:
.\.venv\Scripts\python.exe SponsorPrototype/extract_csv.py
```

The script reads `PDF_DIR` from `.env` (default `pdf/`) and uses titles, DOIs, and
collections from `manifest.json`. A normal PDF folder is also supported:

```powershell
.\.venv\Scripts\python.exe SponsorPrototype/extract_csv.py --pdf-dir C:\papers --model gemma3:1b --output .extraction-runs\my-run.csv
```

By default each run creates `.extraction-runs/<run>/pv_extraction_results.csv` and
`pv_extraction_results.responses.jsonl`. CSVs use UTF-8 with a BOM for Excel, keep
the original 27 display labels, and add source, model, status, selected chunk,
filled-field count, cell evidence, and error columns. A rerun refuses to overwrite existing files.
Each finished paper is flushed to disk; stopping a run retains already saved rows.
Raw logs contain the exact prompt/excerpt, response, and error for every attempt,
linked by source PDF and chunk number. These private artifacts are ignored by Git
when saved under `.extraction-runs/`.

Performance values are numeric strings in the requested column units. Known matching
unit suffixes are stripped; unreported units/conversions remain `N/A`. Evidence is
constrained to literal text windows around efficiency mentions (including the Greek
eta symbol). Chunks without those mentions leave performance fields as `N/A`.
Invented quotes and performance numbers absent from
the excerpt are rejected before candidate selection. These checks establish text
support, but do not establish that a number represents the correct device or metric.

The script uses 4,000-character chunks with 200-character overlap, temperature 0,
and an 8,192-token context. `--chunk-size`, `--chunk-overlap`, `--context-size`,
`--timeout`, `--retries`, `--ollama-url`, and `--model` override these settings.
If multiple chunks have data, it selects the candidate with the highest unambiguous
numeric cell efficiency, breaking ties by filled-field count. Without a comparable
efficiency it selects the most filled candidate. It keeps a single chunk's values
together instead of combining potentially different devices. Some fields elsewhere
in the article may therefore remain unavailable.

`Status` distinguishes `extracted`, `partial` (some chunks failed), `no_data`
(valid responses containing only `N/A`), `partial_no_data`, `no_text` (OCR needed),
and `failed`. Exit code 0 means every paper has a populated result; 2 means the CSV
was saved but some papers have partial/missing/failed results; 1 is a setup/output
error. Structured JSON prevents formatting failures but does not verify scientific
accuracy. Review extracted values against the selected source excerpt; the small
`gemma3:1b` model can still miss or invent values. You can select another locally
installed model using `--model`.

## Download the paper corpus

From the repository root on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r SponsorPrototype/requirements-zotero.txt
Copy-Item .env.example .env  # First setup only; retain an existing .env.
```

Set `ZOTERO_API_KEY` in `.env`. The settings select the `PV-Opto-KG` group and a
reproducible random sample of **20 papers per collection** from `Si-PERC`, `Si-SHJ`,
and `Si-TOPCon`. Names are matched without regard to case. `ZOTERO_GROUP_ID` is optional;
when omitted, the downloader discovers the named group from the key's accessible groups.

```powershell
.\.venv\Scripts\python.exe SponsorPrototype/pipeline.py download
.\.venv\Scripts\python.exe SponsorPrototype/pipeline.py status
```

Only `download` and `status` are available. `--count` changes the number per collection;
`--seed` changes the reproducible random sample. Successful downloads are reused on retry.
Unavailable stored PDF attachments are reported and replaced by the next candidate.
An incomplete sample produces a nonzero exit code. Nested collections are included.
An article shared by collections counts toward each collection but is downloaded once.

PDFs are saved in `pdf/<collection>/`. `pdf/manifest.json` records titles, authors, DOIs,
Zotero item and attachment keys, collection membership, file hashes, and download counts.
Paths in `.env` resolve relative to the repository, regardless of the working directory.

The Zotero client uses GET requests only. It does not change the group library or scrape
publisher pages. The API key is sent only to Zotero and is not forwarded to attachment
storage redirects. Credentials, PDF folders, PDFs, virtual environments, and generated
caches are ignored by Git.

## Original extraction

The sponsor's `requirements.txt`, `environment.yml`, `run.sh`, and extraction code are
preserved. The original extractor uses `gemma3:1b`, expects a `foldersam` directory relative
to its working directory, and recursively finds PDF subfolders. Downloads stay in `pdf/`;
the retrieval command does not connect these paths or start extraction automatically.

The original extractor still uses 6,000-character chunks with a 200-character overlap,
selects the response with the most filled fields, validates through its original
Pydantic model, and writes `pv_extraction_results_ollama.csv`. No custom evidence schema,
alternative candidate selection, extraction checkpoints, or JSON/SQLite extraction
exports are used in the original script. The dashboard can still observe this
original process when launched with `--extractor original`.

## Extraction dashboard

The local dashboard shows the paper corpus, model progress, and saved CSV results.
Its pale blue surfaces, charcoal workspace, rounded panels, and lime accents
follow the supplied design reference. The Marimo theme was removed. The original
`PV-Work/mainScript/extraction.py` is identical to the sponsor's Git version.

The restored visual contract lives in `dashboard/static/style.css`: page `#e8f0fd`,
panels `#d7e4ef`, selected-paper detail `#aec5d1`, ink `#203038`, charcoal `#303631`,
lime `#dafa58`, muted text `#4c606d`, and focus outline `#476817`. It uses system
Segoe UI at 14px, a 42px desktop title (34px on mobile), 24px horizontal overview
panel padding, and a 26px workspace radius. At 800px and below, the overview and
paper/detail workspace stack vertically. This preserves the supplied reference's
visual direction; no new design direction was chosen.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r SponsorPrototype/requirements-dashboard.txt
ollama pull gemma3:1b
.\.venv\Scripts\python.exe SponsorPrototype/dashboard/server.py
```

Open `http://127.0.0.1:2718/`. The Python server serves both the backend API and the
HTML/CSS/JavaScript frontend. No separate Node server or frontend build is needed.
Ollama must be running to start a new extraction; importing a saved CSV works without it.

Use **Extract all 60 papers** (the count reflects the current corpus) or select a paper
and choose **Extract selected paper**. **Stop** terminates the worker. Each completed
paper's row is published atomically, so **Download CSV** remains available for already
saved rows during a run or after stopping it. Starting again creates a fresh run.

To display the saved one-document sample without calling the model again:

```powershell
.\.venv\Scripts\python.exe SponsorPrototype/dashboard/server.py --import-csv .extraction-runs/sample/pv_extraction_results.csv
```

Imports verify source filenames against the corpus manifest and preserve the exact
CSV bytes. The dashboard opens Results when rows exist. Run progress distinguishes
one processed document from the full 60-paper corpus; the other 59 are marked **Not run**.
The table shows paper, collection, status, populated-field count, and efficiency. Select
a result to inspect all 27 article fields, grouped into research, device/materials,
surfaces/contacts, and performance. Metadata columns are not counted as article fields.
Partial results retain missing values and display a review note. Source evidence and
extraction issues are expandable. All model values still require review against the paper.

### Workers and storage

- `dashboard/server.py` stages selected PDFs using hard links or copies into a private
  `.dashboard-runs/<run>/foldersam/` directory and preserves previous runs.
- `dashboard/structured_worker.py` runs `extract_csv.py` and publishes paper/chunk
  progress, saved rows, partial outcomes, and errors through atomic state/CSV updates.
- `dashboard/results.py` associates each structured row by its source PDF and keeps
  the 27 article fields separate from CSV metadata.
- `--extractor original` launches `dashboard/observer.py`, which runs the unmodified
  sponsor script. Its original prompts, parser, selection rules, and no-CSV behavior
  for runs without accepted results remain available.
- Dashboard restarts mark an unfinished run as interrupted. Structured rows already
  published remain downloadable; a subsequent extraction starts from the beginning.

The dashboard serves only on `127.0.0.1`, accepts job actions only from its own origin,
and requires no frontend framework or external assets. Its compatible runtime pins are
in `requirements-dashboard.txt`; the sponsor's requirements and environment files remain
unchanged. `.env`, PDF folders, staged PDFs, logs, state, and generated CSV files in
`.dashboard-runs/` are excluded from Git. The Zotero client continues to use GET only.

### Changes and reasons

| Change | Purpose | Relationship to the original extraction |
| --- | --- | --- |
| Read-only Zotero downloader and `.env.example` | Retrieve 20 PDFs per collection into the private corpus | Input acquisition only; no LLM or CSV generation |
| Dashboard HTML/CSS/JavaScript | Show the queue, actual progress, selected paper values, and final CSV using the supplied design | Presentation only |
| Local server, structured worker, and trace observer | Launch extraction, import saved CSVs, and report progress | Structured extraction is the default; the unmodified original worker remains selectable |
| Removed Marimo stylesheet/configuration | Restore the requested dashboard and original notebook | Original extractor restored exactly |
| Ignore rules | Keep credentials, source papers, and run artifacts off GitHub | No change to extraction behavior |
| Dashboard tests and runtime pins | Verify source preservation, accurate progress, exact CSV downloads, and local request boundaries | Tests compare observed/unobserved original CSV bytes using deterministic transport fixtures |

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s SponsorPrototype/tests -v
```

Retrieval tests cover Zotero pagination, PDF download
validation, and credential handling on storage redirects. Dashboard tests verify the
original entry point and source hash, one progress increment per model call, correct
paper-to-row association, exact CSV download bytes and quoted values, corpus path
boundaries, and rejection of cross-origin job actions. A deterministic transport fixture
compares the original script's CSV bytes with and without the observer while retaining
its prompts, splitter, chain, parser, selection, and CSV writer.
Dashboard tests also cover importing a BOM CSV, preserving its partial status and exact
download bytes, matching rows to source papers, restoring imported runs, downloading
saved rows after stop, and structured worker progress/CSV publication.
The separate CSV extractor tests reject null/schema echoes, malformed JSON, and
invented performance numbers/quotes,
exercise the real HTTP transport against a local fixture server, verify retries and
raw-response provenance, preserve quoted CSV values, check missing/failed/no-text
rows and partial results, and compare the field labels to the original schema.

Passing these tests verifies retrieval and dashboard behavior; it does not establish the
quality of live Gemma extraction. A live parsed response may contain only `N/A`, and an
entire run may finish without accepted rows or a CSV under the original rules.
