"""Run the structured extractor and publish completed CSV rows atomically."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_csv import run
from dashboard.observer import save
from dashboard.results import CSV_NAME, apply_row


def publish_csv(directory):
    temporary = directory / 'published.tmp'
    temporary.write_bytes((directory / 'worker.csv').read_bytes())
    for attempt in range(8):
        try:
            temporary.replace(directory / CSV_NAME)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.025)


def work(directory):
    path = directory / 'state.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    papers = [dict(paper, path=directory / 'foldersam' / paper['pdf_path'])
              for paper in state['papers']]
    by_path = {paper['pdf_path']: paper for paper in state['papers']}

    def event(kind, source, detail):
        paper = by_path[source['pdf_path']]
        state['current_id'] = paper['paper_id']
        if kind == 'reading':
            paper.update(status='reading', started_at=time.time())
        elif kind == 'chunk':
            paper.update(status='model', **detail)
        elif kind == 'saved':
            publish_csv(directory)
            apply_row(paper, detail['row'], detail['row_index'])
            paper['finished_at'] = time.time()
            state['processed'] += 1
            state['accepted'] += int(detail['row']['Filled Fields']) > 0
        state['updated_at'] = time.time()
        save(path, state)

    args = SimpleNamespace(pdf_dir=directory / 'foldersam', output=directory / 'worker.csv',
                           limit=None, model=state['model'], ollama_url='http://127.0.0.1:11434',
                           timeout=180, retries=1, chunk_size=4000, chunk_overlap=200,
                           context_size=8192)
    state['status'] = 'running'
    save(path, state)
    try:
        code = run(args, papers=papers, on_event=event)
        state['status'] = 'completed' if code == 0 else 'completed_with_issues'
        state['message'] = f"Saved {state['processed']} paper rows. Review model values against the source papers."
    except Exception as error:
        state.update(status='failed', message=f'{type(error).__name__}: {error}')
        traceback.print_exc()
        code = 1
    state['finished_at'] = time.time()
    save(path, state)
    return code


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    sys.exit(work(parser.parse_args().run_dir.resolve()))
