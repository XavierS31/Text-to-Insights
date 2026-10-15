"""Launch the durable structured extractor; JSON files remain compatibility exports."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_csv import run
from extraction_store import Store
from dashboard.observer import save


def work(directory, retry_failed=False):
    path = directory / 'state.json'
    initial = json.loads(path.read_text(encoding='utf-8'))
    store = Store(initial['database'])
    record = store.load(initial['run_id'])
    args = SimpleNamespace(**{k:v for k,v in record['config'].items() if k not in ('version','implementation')},
                           database=store.path, run_id=initial['run_id'],
                           pdf_dir=directory / 'foldersam', output=Path(record['state']['output_path']),
                           limit=None, retry_failed=retry_failed,resume_existing=True)
    def event(*unused):
        save(path,store.load(args.run_id)['state'])
    try:
        return run(args,on_event=event)
    finally:
        save(path,store.load(args.run_id)['state'])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8',errors='backslashreplace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--retry-failed',action='store_true')
    options = parser.parse_args()
    sys.exit(work(options.run_dir.resolve(),options.retry_failed))
