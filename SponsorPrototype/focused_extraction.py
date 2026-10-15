"""Small, bounded Gemma requests within the existing per-chunk extraction pipeline."""
import json
import socket
from urllib.error import HTTPError, URLError

from extraction_store import fingerprint
from extract_csv import (COLUMN_MAP, PERFORMANCE_FIELDS, RESPONSE_FIELDS, SYSTEM_PROMPT,
                         chunk_schema, normalize_text, ollama_chat, validate_content,
                         validate_grounding)


class OllamaUnavailable(ConnectionError):
    """Interrupt the run, retaining queued work and committed checkpoints."""


FIELDS = list(COLUMN_MAP)
GROUPS = (
    ('Research', FIELDS[:2]),
    ('Device and doping', FIELDS[2:9]),
    ('Front surfaces', [k for k in FIELDS[9:17] if k.startswith('front_')]),
    ('Rear surfaces', [k for k in FIELDS[9:17] if k.startswith('rear_')]),
    ('Contacts', FIELDS[17:21]),
)


def value_limit(key):
    if key in ('research_focus', 'key_findings'):
        return 240
    if key in PERFORMANCE_FIELDS or key == 'evidence_id':
        return 32
    return 120


def extract(chunk, number, paper, args, raw_log):
    errors = []
    result = dict.fromkeys(RESPONSE_FIELDS, 'N/A')
    choices = {f'E{i}': quote for i, quote in enumerate(
        chunk_schema(chunk)['properties']['cell_evidence']['enum'][1:], 1)}
    store = getattr(args, 'store', None)
    run_id = getattr(args, 'run_id', None)
    paper_id = paper.get('paper_id', paper['pdf_path'])
    anchor = 'N/A'

    def notify(group, **detail):
        callback = getattr(args, 'on_task', None)
        if callback:
            callback('task', paper, dict(chunk=number, group=group, **detail))

    def validate(data, keys):
        if not isinstance(data, dict) or set(data) != set(keys):
            raise ValueError('invalid_json: return exactly the requested object keys.')
        if any(not isinstance(v, str) for v in data.values()):
            raise ValueError('invalid_json: all values must be strings.')
        for key, value in data.items():
            if len(value) > value_limit(key):
                raise ValueError(f'unsupported_value: {key} is too long; use a concise value or N/A.')
        base = dict.fromkeys(RESPONSE_FIELDS, 'N/A')
        base.update({key: value for key,value in data.items() if key != 'evidence_id'})
        evidence_id = data.get('evidence_id')
        if evidence_id is not None:
            if evidence_id not in ('N/A', *choices):
                raise ValueError('unsupported_value: unknown evidence ID.')
            base['cell_evidence'] = choices.get(evidence_id, 'N/A')
            if (evidence_id == 'N/A') != (base['efficiency_percent'] == 'N/A'):
                raise ValueError('unsupported_value: provide both an efficiency and its evidence ID, or both N/A.')
        else:
            base['cell_evidence'] = choices.get(anchor, 'N/A')
        base = validate_content(json.dumps(base))
        validate_grounding(base, chunk)
        if any(k in PERFORMANCE_FIELDS for k in keys) and evidence_id is None:
            # The remaining measurements must be supported by the selected window,
            # not merely by an unrelated number elsewhere in the chunk.
            validate_grounding(base, choices.get(anchor, ''))
        cleaned = {key: base[key] for key in keys if key != 'evidence_id'}
        if evidence_id is not None:
            cleaned['evidence_id'] = evidence_id
        return cleaned

    def task(group, keys, context='', split=True):
        error_start = len(errors)
        key = fingerprint(dict(chunk=chunk, number=number, group=group, fields=keys, anchor=anchor,
                               context=context, pdf=paper.get('pdf_hash'), config=getattr(args,'config_hash','')))
        previous = store.checkpoint(run_id, paper_id, key) if store else None
        if previous:
            errors.extend(previous['errors'])
            notify(group, cached=True)
            if previous['status'] == 'valid':
                return validate(previous['data'], keys)
            return None
        properties = {field: {'type':'string','maxLength':value_limit(field)} for field in keys}
        if 'evidence_id' in keys:
            properties['evidence_id']['enum'] = ['N/A', *choices]
        schema = dict(type='object',properties=properties,required=keys,additionalProperties=False)
        local_errors = []
        correction = ''
        for attempt in range(1, min(getattr(args,'retries',1),1) + 2):
            notify(group, attempt=attempt, cached=False)
            prompt = ('Return only these fields as JSON strings. Use N/A when unreported. '
                      'Keep summaries below 240 characters and other text below 120 characters.\n'
                      + json.dumps(schema, ensure_ascii=False) + '\n' + context + '\n'
                      + correction + '\nARTICLE EXCERPT:\n' + chunk)
            payload = dict(model=args.model, stream=False, format=schema,
                           messages=[{'role':'system','content':SYSTEM_PROMPT.replace(
                               'cell_evidence must be a short EXACT quote from this excerpt supporting the selected\ncell\'s performance, including its reported efficiency. Never invent or paraphrase this\nquote. For a table quote, include its relevant header and row as one continuous excerpt.',
                               'Choose evidence_id from the supplied IDs; never generate an evidence quotation.')},
                                     {'role':'user','content':prompt}],
                           options=dict(temperature=0,num_ctx=args.context_size,
                                        num_predict=getattr(args,'num_predict',1024)))
            record = dict(source_pdf=paper['pdf_path'],chunk=number,group=group,attempt=attempt,
                          model=args.model,request=payload)
            data = None
            unavailable = False
            try:
                response = ollama_chat(args.ollama_url, payload, args.timeout)
                record['response'] = response
                if response.get('error'):
                    raise ValueError(str(response['error']))
                if response.get('done_reason') == 'length' or response.get('done') is not True:
                    raise ValueError('output_limit: unfinished response; retrying a smaller task.')
                data = validate(json.loads(response.get('message',{}).get('content','')),keys)
                record['valid'] = True
            except HTTPError as error:
                try:
                    detail = error.read().decode('utf-8', errors='replace')
                finally:
                    error.close()
                unavailable = error.code in (404,502,503,504)
                kind = 'repetition' if 'repeat' in detail.lower() else 'http_error'
                record['error'] = f'{kind}: HTTP {error.code}: {detail[:500]}'
            except (socket.timeout, TimeoutError) as error:
                record['error'] = f'timeout: {error}'
            except (URLError, ConnectionError) as error:
                unavailable = True
                record['error'] = f'unavailable: {error}'
            except (ValueError, TypeError, AttributeError, OSError) as error:
                record['error'] = f'{type(error).__name__}: {error}'
            finally:
                raw_log.write(json.dumps(record,ensure_ascii=False)+'\n')
                raw_log.flush()
                if store:
                    store.save_attempt(run_id,paper_id,key,record,data,local_errors)
            if data is not None:
                return data
            message = f'Chunk {number}, {group}, attempt {attempt}: {record["error"]}'
            local_errors.append(message)
            errors.append(message)
            print('    '+message,flush=True)
            if unavailable:
                raise OllamaUnavailable('Ollama unavailable. Start Ollama and resume this run.')
            correction = ('Previous response failed: '+record['error'][:160]
                          +'. Use N/A for unsupported information; never guess.\n')
        if split and len(keys) > 1:
            notify(group, recovering=True)
            middle = len(keys)//2
            left = task(group+' / A',keys[:middle],context)
            right = task(group+' / B',keys[middle:],context)
            data = dict(left,**right) if left is not None and right is not None else None
        if store:
            store.save_task(run_id,paper_id,key,data,errors[error_start:])
        return data

    if choices:
        performance = task('Performance evidence',['evidence_id','efficiency_percent'],
                           'Choose the highest measured efficiency of the authors\' fabricated cell, '
                           'excluding citations, simulations, modules and background. Exact windows:\n'
                           +json.dumps(choices,ensure_ascii=False),split=False)
        if performance is None:
            return None,errors
        anchor = performance['evidence_id']
        result['efficiency_percent'] = performance['efficiency_percent']
        result['cell_evidence'] = choices.get(anchor,'N/A')
        if anchor != 'N/A':
            values = task('Cell measurements',list(PERFORMANCE_FIELDS[1:]),
                          'Extract only measurements of this selected cell from this exact window: '
                          +result['cell_evidence'])
            if values is None:
                return None,errors
            result.update(values)
    context = ('All device fields must describe this selected measured cell: '+result['cell_evidence']
               if anchor != 'N/A' else 'No measured performance is selected in this excerpt. Do not infer measurements.')
    for group,keys in GROUPS:
        values = task(group,keys,context)
        if values is None:
            return None,errors
        result.update(values)
    validate_grounding(result,chunk)
    return result,errors
