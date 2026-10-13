"""Read-only PDF retrieval: python SponsorPrototype/pipeline.py download|status."""
import argparse
import json
import sys

from pv_pipeline.config import Settings
from pv_pipeline.ingest import download_sample
from pv_pipeline.storage import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only Zotero PDF retrieval')
    parser.add_argument('command', choices=['download', 'status'])
    parser.add_argument('--count', type=int, help='Papers per collection (default: 20)')
    parser.add_argument('--seed', type=int, help='Seed for reproducible random sampling')
    args = parser.parse_args(argv)
    settings = Settings.load()
    if args.count is not None:
        if args.count < 1:
            parser.error('--count must be positive')
        settings.count = args.count
    if args.seed is not None:
        settings.seed = args.seed
    try:
        if args.command == 'status':
            manifest = read_json(settings.pdf_dir / 'manifest.json', {})
            print(json.dumps({'collections': manifest.get('collections', []),
                              'unique_papers': len(manifest.get('papers', [])),
                              'complete': manifest.get('complete', False)}, indent=2))
            return 0
        manifest = download_sample(settings)
        if not manifest['complete']:
            print('Sample is incomplete; inspect pdf/manifest.json for shortfalls.', file=sys.stderr)
            return 2
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f'Pipeline stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
