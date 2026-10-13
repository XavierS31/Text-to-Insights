"""Local dashboard for structured extraction, CSV review, and the original worker."""
import argparse
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import uuid

SPONSOR = Path(__file__).resolve().parents[1]
ROOT = SPONSOR.parent
sys.path.insert(0, str(SPONSOR))
from pv_pipeline.config import Settings
from dashboard.observer import SOURCE, save
from dashboard.results import CSV_NAME as STRUCTURED_CSV_NAME, FIELD_COLUMNS, apply_row

STATIC = Path(__file__).resolve().parent / 'static'
RUNS = ROOT / '.dashboard-runs'
CSV_NAME = 'pv_extraction_results_ollama.csv'


class Jobs:
    def __init__(self, extractor='structured'):
        self.extractor = extractor
        self.pdf_dir = Settings.load().pdf_dir.resolve()
        self.lock = threading.RLock()
        self.process = None
        RUNS.mkdir(exist_ok=True)
        pointer = RUNS / 'latest.json'
        self.directory = None
        if pointer.exists():
            run_id = json.loads(pointer.read_text())['run_id']
            if (RUNS / run_id).is_dir() and Path(run_id).name == run_id:
                self.directory = RUNS / run_id
                state = self.read_run()
                if state.get('status') in ('starting', 'running'):
                    state.update(status='interrupted', message='The dashboard restarted. Start a new run to extract the corpus again.')
                    for paper in state['papers']:
                        if paper['status'] in ('reading', 'model'):
                            paper['status'] = 'interrupted'
                    save(self.directory / 'state.json', state)

    def corpus(self):
        manifest = self.pdf_dir / 'manifest.json'
        if not manifest.exists():
            return []
        papers = json.loads(manifest.read_text(encoding='utf-8')).get('papers', [])
        available = []
        for paper in papers:
            path = (self.pdf_dir / paper['pdf_path']).resolve()
            if path.is_relative_to(self.pdf_dir) and path.is_file() and path.suffix.lower() == '.pdf':
                available.append({k: paper.get(k, '') for k in ('paper_id', 'title', 'doi', 'authors', 'collections', 'pdf_path', 'zotero_url')})
        return available

    def read_run(self):
        return json.loads((self.directory / 'state.json').read_text(encoding='utf-8')) if self.directory else None

    def csv_path(self, state):
        name = state.get('csv_name', CSV_NAME)
        if name not in (CSV_NAME, STRUCTURED_CSV_NAME):
            raise ValueError('Invalid dashboard CSV name.')
        return self.directory / name

    def import_csv(self, source):
        """Import a saved structured result; never trigger another model extraction."""
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError('Stop the active extraction before importing results.')
            source = source.resolve()
            with source.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                if not {'Source PDF', 'Status', *FIELD_COLUMNS}.issubset(reader.fieldnames or []):
                    raise ValueError('Import a CSV created by extract_csv.py with source and status columns.')
                rows = list(reader)
            if not rows:
                raise ValueError('The CSV contains no paper rows.')
            papers = [dict(paper, status='not_run', chunk=0, chunks=0) for paper in self.corpus()]
            by_path = {paper['pdf_path']: paper for paper in papers}
            seen = set()
            for index, row in enumerate(rows):
                if row['Source PDF'] not in by_path or row['Source PDF'] in seen:
                    raise ValueError('CSV sources must uniquely match downloaded PDFs in the manifest.')
                if row['Status'] not in ('extracted', 'partial', 'no_data', 'partial_no_data', 'no_text', 'failed'):
                    raise ValueError('Invalid extraction status in CSV.')
                apply_row(by_path[row['Source PDF']], row, index)
                seen.add(row['Source PDF'])
            run_id = 'import-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
            directory = RUNS / run_id
            directory.mkdir()
            shutil.copyfile(source, directory / STRUCTURED_CSV_NAME)
            raw = source.with_suffix('.responses.jsonl')
            if raw.is_file():
                shutil.copyfile(raw, directory / 'responses.jsonl')
            issues = any(row['Status'] != 'extracted' for row in rows)
            state = dict(run_id=run_id, status='completed_with_issues' if issues else 'completed',
                         extractor='structured', csv_name=STRUCTURED_CSV_NAME, imported=True,
                         imported_from=str(source), finished_at=time.time(), run_total=len(rows),
                         processed=len(rows), accepted=sum(any(row[field] != 'N/A' for field in FIELD_COLUMNS) for row in rows),
                         model=rows[0].get('Model', 'gemma3:1b'), papers=papers,
                         current_id=by_path[rows[0]['Source PDF']]['paper_id'], columns=[],
                         message=f'Loaded results for {len(rows)} document(s) from a saved CSV. Review the model values against the paper.')
            save(directory / 'state.json', state)
            (directory / 'run.log').write_text('Imported saved CSV; no extraction was rerun.\n', encoding='utf-8')
            save(RUNS / 'latest.json', {'run_id': run_id})
            self.directory = directory
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            state = self.read_run()
            papers = self.corpus()
            if state is None:
                state = dict(status='idle', papers=[], processed=0, accepted=0, current_id=None, model='gemma3:1b', columns=[], message='Ready to extract the downloaded papers.', run_total=0, extractor=self.extractor)
            state.setdefault('run_total', len(state['papers']))
            run_papers = {paper['paper_id']: paper for paper in state['papers']}
            state['papers'] = [run_papers.get(paper['paper_id'], dict(paper, status='not_run', chunk=0, chunks=0)) for paper in papers] + [paper for key, paper in run_papers.items() if not any(item['paper_id'] == key for item in papers)]
            state['corpus_count'] = len(papers)
            state['csv_name'] = state.get('csv_name', CSV_NAME)
            state['worker'] = self.extractor
            state['field_columns'] = FIELD_COLUMNS if state.get('extractor') == 'structured' else state['columns']
            state['csv_available'] = False
            state['rows'] = []
            if self.directory and self.csv_path(state).is_file() and (state.get('extractor') == 'structured' or state['status'] == 'completed'):
                with self.csv_path(state).open(encoding='utf-8-sig', newline='') as handle:
                    reader = csv.DictReader(handle)
                    state['columns'] = reader.fieldnames
                    state['rows'] = list(reader)
                state['csv_available'] = bool(state['rows'])
                if state.get('extractor') != 'structured':
                    state['field_columns'] = state['columns']
            state['elapsed'] = round((state.get('finished_at') or time.time()) - state['started_at']) if state.get('started_at') else 0
            if self.directory:
                log = self.directory / 'run.log'
                if log.exists():
                    with log.open('rb') as handle:
                        handle.seek(max(0, log.stat().st_size - 12000))
                        state['log'] = handle.read().decode('utf-8', errors='replace')
            return state

    def start(self, paper_id=None):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                raise ValueError('An extraction is already running.')
            papers = self.corpus()
            if paper_id is not None:
                papers = [paper for paper in papers if paper['paper_id'] == paper_id]
            if not papers:
                raise ValueError('No downloaded PDFs were found in the manifest.')
            try:
                with urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as response:
                    models = json.load(response).get('models', [])
                if not any(m['name'] == 'gemma3:1b' for m in models):
                    raise ValueError('Download gemma3:1b in Ollama before starting.')
            except OSError as error:
                raise ValueError('Ollama is unavailable at localhost:11434. Start Ollama and retry.') from error
            run_id = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
            directory = RUNS / run_id
            directory.mkdir()
            # Map the downloaded corpus to the original relative input name; do not edit constants.
            for paper in papers:
                source = self.pdf_dir / paper['pdf_path']
                target = directory / 'foldersam' / paper['pdf_path']
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, target)
                except OSError:
                    shutil.copyfile(source, target)
            state = dict(run_id=run_id, status='starting', started_at=time.time(), processed=0, accepted=0, current_id=None, model='gemma3:1b', columns=[], message='', papers=[dict(p, status='queued', chunk=0, chunks=0) for p in papers], source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest())
            state.update(extractor=self.extractor, run_total=len(papers),
                         csv_name=STRUCTURED_CSV_NAME if self.extractor == 'structured' else CSV_NAME)
            save(directory / 'state.json', state)
            save(RUNS / 'latest.json', {'run_id': run_id})
            with (directory / 'run.log').open('wb') as log:
                worker = 'structured_worker.py' if self.extractor == 'structured' else 'observer.py'
                self.process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name(worker)), '--run-dir', str(directory)], stdout=log, stderr=subprocess.STDOUT, cwd=directory, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.directory = directory
            threading.Thread(target=self.monitor, args=(self.process, directory), daemon=True).start()
            return self.snapshot()

    def monitor(self, process, directory):
        code = process.wait()
        with self.lock:
            state = json.loads((directory / 'state.json').read_text(encoding='utf-8'))
            if state['status'] in ('starting', 'running'):
                state.update(status='failed', finished_at=time.time(), message=f'Extractor exited with code {code}; see the run log.')
                save(directory / 'state.json', state)

    def stop(self):
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return self.snapshot()
            process.terminate()
            process.wait(timeout=10)
            state = self.read_run()
            state.update(status='stopped', finished_at=time.time(), message='Extraction stopped. A new run starts from the beginning.')
            for paper in state['papers']:
                if paper['status'] in ('reading', 'model'):
                    paper['status'] = 'stopped'
            save(self.directory / 'state.json', state)
            return self.snapshot()


def handler(jobs):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, payload, code=200, content_type='application/json', filename=None):
            data = json.dumps(payload, ensure_ascii=False).encode() if content_type == 'application/json' else payload
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                if self.path == '/api/state':
                    return self.respond(jobs.snapshot())
                if self.path == '/api/csv':
                    with jobs.lock:
                        state = jobs.snapshot()
                        if not state['csv_available']:
                            return self.respond({'error': 'No paper rows have been saved yet.'}, 404)
                        return self.respond(jobs.csv_path(state).read_bytes(), content_type='text/csv; charset=utf-8', filename=state['csv_name'])
                paths = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}
                if self.path not in paths:
                    return self.respond({'error': 'Not found'}, 404)
                file = STATIC / paths[self.path]
                return self.respond(file.read_bytes(), content_type=mimetypes.guess_type(str(file))[0] or 'text/plain')
            except (OSError, ValueError) as error:
                self.respond({'error': str(error)}, 500)

        def do_POST(self):
            # JSON + same-origin checks prevent another website from starting local jobs.
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host or self.headers.get('Origin') != f'http://{host}' or self.headers.get('Content-Type') != 'application/json':
                return self.respond({'error': 'Only same-origin dashboard requests are accepted.'}, 403)
            try:
                if self.path == '/api/start':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 <= length <= 4096:
                        raise ValueError('Invalid request size.')
                    body = json.loads(self.rfile.read(length) or b'{}')
                    if not isinstance(body, dict) or (body.get('paper_id') is not None and not isinstance(body['paper_id'], str)):
                        raise ValueError('Choose a valid paper.')
                    return self.respond(jobs.start(body.get('paper_id')))
                if self.path == '/api/stop':
                    return self.respond(jobs.stop())
                self.respond({'error': 'Not found'}, 404)
            except ValueError as error:
                self.respond({'error': str(error)}, 409)
            except OSError as error:
                self.respond({'error': str(error)}, 500)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=2718)
    parser.add_argument('--extractor', choices=['structured', 'original'], default='structured')
    parser.add_argument('--import-csv', type=Path, help='Load an existing structured CSV as the displayed run.')
    args = parser.parse_args()
    jobs = Jobs(extractor=args.extractor)
    if args.import_csv:
        jobs.import_csv(args.import_csv)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(jobs))
    print(f'Extraction dashboard: http://127.0.0.1:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        jobs.stop()
        server.server_close()
