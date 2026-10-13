# Sponsor prototype and read-only Zotero retrieval

The sponsor's original extraction architecture is unchanged:

`PDFMinerLoader → RecursiveCharacterTextSplitter → LangChain/Ollama → Pydantic parser → pandas CSV`

The added downloader is a separate ingestion step. It does not call an LLM, parse article
text, select extraction results, or generate CSV files. Original prompts, schema, chunking,
result selection, and CSV columns remain in `PV-Work/mainScript/extraction.py`.

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
exports are used. The dashboard below observes this original process.

## Extraction dashboard

The local dashboard restores the paper queue, model progress, parsed values, and original
CSV results. Its pale blue surfaces, charcoal workspace, rounded panels, and lime accents
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

Open `http://127.0.0.1:2718/`. No Marimo password is needed. Ollama must be running locally.
Use **Start extraction** to run all downloaded papers, **Stop** to terminate the worker,
and **Download CSV** after the original extractor has finished writing its output.
Collection filters and paper selection let you inspect individual papers; the Results
view shows the original CSV's 27 columns without adding or renaming fields.
These controls use native HTML buttons, with visible keyboard focus and selected
states for the views, collection filters, and papers.

### How the dashboard preserves extraction

- `dashboard/server.py` stages hard links (copies if hard links are unavailable) from
  `pdf/` into `.dashboard-runs/<run>/foldersam/`. This gives the original script its
  expected relative input folder without modifying its constants or the source PDFs.
- `dashboard/observer.py` executes the original entry point through `runpy.run_path`.
  A Python trace observer reads the original function's locals to display the paper,
  chunk, parsed response, selected result, and handled errors. It does not replace or
  patch the model, prompt, splitter, parser, selection rules, or CSV writer.
- Parsed chunk values are labelled as pending until the original extractor selects
  them. Live accepted values reflect its original results list. Final results and CSV
  downloads read the original output file; the download returns its exact bytes.
- The original script silently continues after chunk/PDF errors. The observer exposes
  those errors and papers with no accepted result, without adding recovery or retries.
  A response containing only `N/A` remains unaccepted under the original selection rule.
- If every paper has no accepted result, the original extractor writes no CSV. The
  dashboard reports **No results** and keeps CSV download unavailable.
- Start creates a fresh run; Stop does not create a partial CSV or resume checkpoint.
  A restarted dashboard reports an unfinished run as interrupted.

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
| Local server and trace observer | Launch the original script and report its progress | Original LLM → parsing → CSV runs unchanged |
| Removed Marimo stylesheet/configuration | Restore the requested dashboard and original notebook | Original extractor restored exactly |
| Ignore rules | Keep credentials, source papers, and run artifacts off GitHub | No change to extraction behavior |
| Dashboard tests and runtime pins | Verify source preservation, accurate progress, exact CSV downloads, and local request boundaries | Tests compare observed/unobserved original CSV bytes using deterministic transport fixtures |

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s SponsorPrototype/tests -v
```

The suite contains nine tests. Retrieval tests cover Zotero pagination, PDF download
validation, and credential handling on storage redirects. Dashboard tests verify the
original entry point and source hash, one progress increment per model call, correct
paper-to-row association, exact CSV download bytes and quoted values, corpus path
boundaries, and rejection of cross-origin job actions. A deterministic transport fixture
compares the original script's CSV bytes with and without the observer while retaining
its prompts, splitter, chain, parser, selection, and CSV writer.

Passing these tests verifies retrieval and dashboard behavior; it does not establish the
quality of live Gemma extraction. A live parsed response may contain only `N/A`, and an
entire run may finish without accepted rows or a CSV under the original rules.
