"""Shared resumable execution for the CLI and dashboard worker."""
from collections import Counter
import json
import os
from pathlib import Path
import time
from urllib.request import urlopen
import uuid

from extraction_store import DEFAULT_DB, VERSION, Store, WorkerLock, file_hash, fingerprint, csv_bytes

DEFAULTS = dict(model='gemma3:1b',ollama_url='http://127.0.0.1:11434',timeout=180,
                retries=1,chunk_size=2500,chunk_overlap=200,context_size=8192,num_predict=1024)
IMPLEMENTATION = fingerprint({name:file_hash(Path(__file__).with_name(name)) for name in
                              ('extract_csv.py','focused_extraction.py','extraction_runtime.py')})


def model_digest(url, model):
    from focused_extraction import OllamaUnavailable
    try:
        with urlopen(url.rstrip('/')+'/api/tags',timeout=5) as response:
            models = json.load(response).get('models',[])
    except OSError as error:
        raise OllamaUnavailable('Ollama unavailable. Start Ollama and resume this run.') from error
    match = next((item for item in models if item['name'] == model),None)
    if not match:
        raise OllamaUnavailable(f'Download {model} in Ollama before starting or resuming.')
    return match['digest']


def configuration(args):
    return dict(version=VERSION,implementation=IMPLEMENTATION,
                **{key:getattr(args,key,value) for key,value in DEFAULTS.items()})


def create_run(store, papers, args, digest, run_id=None, directory=None):
    from extract_csv import META_COLUMNS, COLUMN_MAP
    run_id = run_id or time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    for paper in papers:
        paper.setdefault('paper_id',paper['pdf_path'])
    state = dict(run_id=run_id,status='starting',started_at=time.time(),updated_at=time.time(),
                 processed=0,accepted=0,current_id=None,model=args.model,columns=META_COLUMNS+list(COLUMN_MAP.values()),
                 field_columns=list(COLUMN_MAP.values()),csv_name='pv_extraction_results.csv',extractor='structured',
                 run_total=len(papers),message='',imported=False,output_path=str(args.output),
                 directory=str(directory or Path(args.output).parent),
                 papers=[dict({k:v for k,v in p.items() if k not in ('path','original_path')},
                              status='queued',chunk=0,chunks=0) for p in papers])
    store.create(state,papers,configuration(args),digest)
    return state


def validate_resume(store, run_id):
    record = store.load(run_id)
    if record['imported']:
        raise ValueError('Imported CSV runs cannot be resumed; start a new extraction.')
    if record['config'].get('version') != VERSION:
        raise ValueError('Extraction version changed; start a new run.')
    if record['config'].get('implementation') != IMPLEMENTATION:
        raise ValueError('Extraction implementation changed; start a new run.')
    config = record['config']
    if model_digest(config['ollama_url'],config['model']) != record['digest']:
        raise ValueError('The Ollama model digest changed; start a new run.')
    for paper in store.sources(run_id):
        for key in ('path','original_path'):
            if paper.get(key) and (not Path(paper[key]).is_file() or file_hash(paper[key]) != paper['pdf_hash']):
                raise ValueError('A source PDF changed or is missing; restore it or start a new run.')
    return record


def run(args, papers=None, on_event=None):
    from extract_csv import discover_papers, extract_paper
    from focused_extraction import OllamaUnavailable
    args.database = Path(getattr(args,'database',DEFAULT_DB))
    store = Store(args.database)
    with WorkerLock(args.database):
        if (getattr(args,'resume',None) or getattr(args,'resume_existing',False)) and getattr(args,'run_id',None) and store.exists(args.run_id):
            record = validate_resume(store,args.run_id)
            if configuration(args) != record['config']:
                raise ValueError('Extraction settings changed; start a new run.')
            state = record['state']
        else:
            papers = discover_papers(args.pdf_dir) if papers is None else papers
            if args.limit:
                papers = papers[:args.limit]
            if not papers:
                raise ValueError(f'No PDF files found in {args.pdf_dir}.')
            if args.output.exists() or args.output.with_suffix('.responses.jsonl').exists():
                raise FileExistsError('CSV or raw log already exists; choose a new --output path.')
            digest = model_digest(args.ollama_url,args.model)
            state = create_run(store,papers,args,digest,getattr(args,'run_id',None))
            args.run_id = state['run_id']
        run_id = args.run_id
        if getattr(args,'retry_failed',False):
            store.clear_failed(run_id)
        args.store = store
        args.config_hash = fingerprint(dict(config=configuration(args),digest=store.load(run_id)['digest']))
        output = Path(state['output_path'])
        args.output = output
        output.parent.mkdir(parents=True,exist_ok=True)
        args.on_task = on_event
        state.update(status='running',finished_at=None,message='Extracting locally with Gemma 1B.',updated_at=time.time())
        store.save_state(state,os.getpid())
        sources = store.sources(run_id)
        by_id = {paper['paper_id']:paper for paper in state['papers']}

        def save():
            state['updated_at'] = time.time()
            store.save_state(state,os.getpid())

        def event(kind, source, detail):
            paper = by_id[source['paper_id']]
            state['current_id'] = paper['paper_id']
            if kind == 'reading':
                paper.update(status='reading',started_at=time.time())
            elif kind == 'chunk':
                paper.update(status='model',**detail)
            elif kind == 'task':
                paper.update(status='model',**detail)
                state['message'] = (f'Chunk {detail["chunk"]} · {detail["group"]}'
                                    + (' · restored checkpoint' if detail.get('cached') else
                                       ' · splitting failed request' if detail.get('recovering') else
                                       f' · attempt {detail.get("attempt",1)}'))
            save()
            if on_event:
                on_event(kind,source,detail)

        args.on_task = event
        try:
            with output.with_suffix('.responses.jsonl').open('a',encoding='utf-8') as raw_log:
                for index,source in enumerate(sources,1):
                    previous = store.result(run_id,source['paper_id'])
                    if previous and (not getattr(args,'retry_failed',False) or
                                     previous['Status'] not in ('partial','partial_no_data','failed')):
                        by_id[source['paper_id']]['status'] = previous['Status']
                        continue
                    paper = dict(source,path=Path(source['path']))
                    paper['pdf_hash'] = source['pdf_hash']
                    print(f'[{index}/{len(sources)}] {paper["title"]}',flush=True)
                    row = extract_paper(paper,args,raw_log,on_event=event)
                    store.save_result(run_id,paper['paper_id'],row)
                    # Recompute from committed results, never increment a counter twice on resume.
                    rows = store.rows(run_id)
                    by_id[paper['paper_id']].update(status=row['Status'],finished_at=time.time())
                    state['processed'] = len(rows)
                    state['accepted'] = sum(int(r['Filled Fields']) > 0 for r in rows)
                    save()
                    store.export(run_id,output)
                    if on_event:
                        on_event('saved',paper,dict(row=row,row_index=rows.index(row)))
                    print(f'  Saved: {row["Status"]}, {row["Filled Fields"]}/27 fields',flush=True)
            rows = store.rows(run_id)
            counts = Counter(row['Status'] for row in rows)
            state.update(status='completed' if counts.get('extracted') == len(sources) else 'completed_with_issues',
                         message=f'Saved {len(rows)}/{len(sources)} papers. Model values require source review.',
                         finished_at=time.time())
            code = 0 if state['status'] == 'completed' else 2
        except (OllamaUnavailable,KeyboardInterrupt) as error:
            state.update(status='interrupted',message=str(error) or 'Interrupted. Resume to continue.',finished_at=time.time())
            code = 3
        except Exception as error:
            state.update(status='failed',message=f'{type(error).__name__}: {error}',finished_at=time.time())
            raise
        finally:
            state['updated_at'] = time.time()
            for paper in state['papers']:
                if state['status'] != 'running' and paper['status'] in ('reading','model'):
                    paper['status'] = 'interrupted'
            store.save_state(state,None)
            store.export(run_id,output)
        print(f'Run: {run_id}\nCSV: {output}\nDatabase: {args.database}\nStatus: {state["status"]}',flush=True)
        return code
