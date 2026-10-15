"""Observe the sponsor's unmodified script; never replace any extraction step."""
import argparse
import hashlib
import json
import linecache
import os
from pathlib import Path
import runpy
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parents[1] / 'PV-Work/mainScript/extraction.py'


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    # Windows readers can momentarily hold the destination open.
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.025)


class Observer:
    def __init__(self, directory):
        self.path = directory / 'state.json'
        self.state = json.loads(self.path.read_text(encoding='utf-8'))
        self.current = None
        self.result_count = 0
        self.main_code = None
        self.column_map = {}
        self.errors = []
        self.main_returned = False

    def publish(self):
        self.state['updated_at'] = time.time()
        save(self.path, self.state)

    def finish_paper(self, results):
        if self.current is None:
            return
        paper = self.state['papers'][self.current]
        if len(results) > self.result_count:
            paper['status'] = 'extracted'
            paper['values'] = {self.column_map[k]: v for k, v in results[-1].items()}
            paper['row_index'] = len(results) - 1
        else:
            paper['status'] = 'no_result'
        paper['error'] = self.errors[-1] if self.errors else ''
        paper['finished_at'] = time.time()
        self.result_count = len(results)
        self.state['processed'] += 1
        self.state['accepted'] = self.result_count

    def trace(self, frame, event, arg):
        if self.main_code is None:
            if event != 'call' or frame.f_code.co_name != 'main':
                return None
            if not {'COLUMN_MAP', 'PDF_FOLDER', 'PROMPT_TEMPLATE'}.issubset(frame.f_globals):
                return None
            self.main_code = frame.f_code
            self.column_map = frame.f_globals['COLUMN_MAP']
            self.state['status'] = 'running'
            self.state['columns'] = list(self.column_map.values())
            self.state['model'] = frame.f_globals['MODEL_NAME']
            self.publish()
        if frame.f_code is not self.main_code:
            return None
        local = frame.f_locals
        results = local.get('results', [])
        if event == 'exception':
            # The original handles these itself. Record them without changing control flow.
            self.errors.append(f'{arg[0].__name__}: {arg[1]}')
            self.errors = self.errors[-5:]
        if event == 'line':
            pdf = local.get('pdf_file')
            if pdf is not None:
                relative = Path(pdf).relative_to('foldersam').as_posix()
                index = next((i for i, p in enumerate(self.state['papers']) if p['pdf_path'] == relative), None)
                if index is not None and index != self.current:
                    self.finish_paper(results)
                    self.current = index
                    self.errors = []
                    paper = self.state['papers'][index]
                    paper.update(status='reading', chunk=0, chunks=0, started_at=time.time())
                    self.state['current_id'] = paper['paper_id']
                    self.publish()
            source_line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
            # The call's opening line is traced twice for a multiline call. Its
            # text argument is evaluated once, immediately before each invocation.
            if self.current is not None and source_line == '"text": chunk,':
                paper = self.state['papers'][self.current]
                paper['status'] = 'model'
                paper['chunks'] = len(local.get('chunks', []))
                paper['chunk'] += 1
                self.publish()
            elif self.current is not None and source_line == 'if cleaned_data:':
                data = local.get('cleaned_data')
                if isinstance(data, dict):
                    self.state['papers'][self.current]['candidate'] = {
                        self.column_map[k]: v for k, v in data.items() if k in self.column_map
                    }
                    self.publish()
        elif event == 'return':
            self.finish_paper(results)
            self.main_returned = True
            self.publish()
        return self.trace


def run(directory):
    observer = Observer(directory)
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    observer.state['source_sha256'] = before
    previous_directory = Path.cwd()
    os.chdir(directory)
    try:
        sys.settrace(observer.trace)
        # This is the original script entry point: app.run() calls its original main once.
        runpy.run_path(str(SOURCE), run_name='__main__')
        sys.settrace(None)
        if not observer.main_returned:
            raise RuntimeError('The original main function did not finish; see the run log.')
        if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != before:
            raise RuntimeError('The extractor source changed during the run.')
        csv_exists = (directory / 'pv_extraction_results_ollama.csv').is_file()
        observer.state['status'] = 'completed' if csv_exists else 'no_results'
        observer.state['message'] = 'Original CSV saved.' if csv_exists else 'The original extractor produced no CSV rows.'
    except Exception as error:
        sys.settrace(None)
        observer.state['status'] = 'failed'
        observer.state['message'] = f'{type(error).__name__}: {error}'
        traceback.print_exc()
    finally:
        observer.state['finished_at'] = time.time()
        observer.publish()
        os.chdir(previous_directory)
    return 1 if observer.state['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from extraction_store import DEFAULT_DB, WorkerLock
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    with WorkerLock(DEFAULT_DB):
        sys.exit(run(args.run_dir.resolve()))
