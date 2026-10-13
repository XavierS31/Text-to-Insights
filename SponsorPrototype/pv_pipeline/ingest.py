import hashlib
from datetime import datetime, timezone
import random
import re

from .storage import read_json, write_json
from .zotero import ZoteroReader

PAPER_TYPES = {'journalArticle', 'conferencePaper', 'bookSection', 'preprint', 'report', 'thesis'}


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def is_pdf(path):
    if not path.exists():
        return False
    with path.open('rb') as handle:
        return b'%PDF-' in handle.read(1024)


def download_sample(settings, emit=print):
    reader = ZoteroReader(settings.api_key)
    group_id = reader.resolve_group(settings.group_name, settings.group_id)
    collections = reader.all(f'/groups/{group_id}/collections')
    by_name = {c['data']['name'].casefold(): c for c in collections}
    missing = [n for n in settings.collections if n.casefold() not in by_name]
    if missing:
        raise ValueError('Collections not found: ' + ', '.join(missing))
    manifest_path = settings.pdf_dir / 'manifest.json'
    previous = read_json(manifest_path, {})
    signature = {'group_id': group_id, 'collections': list(settings.collections),
                 'papers_per_collection': settings.count, 'seed': settings.seed}
    reuse = previous.get('sample') == signature
    manifest = previous if reuse else {
        'sample': signature, 'group_name': settings.group_name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'read_only': True, 'papers': [], 'collections': [], 'skipped': [],
    }
    existing = {p['paper_id']: p for p in manifest['papers']}
    for requested in settings.collections:
        collection = by_name[requested.casefold()]
        name, key = collection['data']['name'], collection['key']
        # Include nested collections. The same article is counted once per requested collection.
        keys = {key}
        changed = True
        while changed:
            before = len(keys)
            keys.update(c['key'] for c in collections if c['data'].get('parentCollection') in keys)
            changed = len(keys) != before
        articles = {}
        for collection_key in sorted(keys):
            for item in reader.all(f'/groups/{group_id}/collections/{collection_key}/items/top'):
                if item['data']['itemType'] in PAPER_TYPES:
                    articles[item['key']] = item
        candidates = sorted(articles.values(), key=lambda a: a['key'])
        random.Random(f'{settings.seed}:{key}').shuffle(candidates)
        chosen = []
        # Keep prior successful selections stable when retrying interrupted downloads.
        old_keys = [p['item_key'] for p in manifest['papers'] if name in p['collections']]
        candidates.sort(key=lambda a: a['key'] not in old_keys)
        emit(f'{name}: {len(candidates)} candidate papers; selecting {settings.count} PDFs.')
        for item in candidates:
            if len(chosen) >= settings.count:
                break
            item_key = item['key']
            paper_id = f'{group_id}_{item_key}'
            data = item['data']
            old = existing.get(paper_id)
            if old and is_pdf(settings.pdf_dir / old['pdf_path']):
                paper = old
            else:
                try:
                    children = reader.all(f'/groups/{group_id}/items/{item_key}/children')
                    attachments = [a for a in children if a['data'].get('itemType') == 'attachment'
                                   and (a['data'].get('contentType') == 'application/pdf'
                                        or a['data'].get('filename', '').lower().endswith('.pdf'))
                                   and a['data'].get('linkMode') in {'imported_file', 'imported_url'}]
                    if not attachments:
                        raise ValueError('No stored PDF attachment available.')
                    downloaded = None
                    for attachment in attachments:
                        slug = re.sub(r'[^A-Za-z0-9_-]', '_', name)
                        relative_path = f'{slug}/{item_key}_{attachment["key"]}.pdf'
                        path = settings.pdf_dir / relative_path
                        try:
                            if not is_pdf(path):
                                reader.download_pdf(group_id, attachment['key'], path)
                            downloaded = (attachment, relative_path, path)
                            break
                        except Exception as error:
                            emit(f'  Attachment {attachment["key"]} unavailable: {type(error).__name__}')
                    if downloaded is None:
                        raise ValueError('All stored PDF attachments were unavailable.')
                    attachment, relative_path, path = downloaded
                    paper = {
                        'paper_id': paper_id, 'item_key': item_key, 'group_id': group_id,
                        'attachment_key': attachment['key'], 'title': data.get('title', item_key),
                        'doi': data.get('DOI', ''), 'date': data.get('date', ''),
                        'authors': [' '.join(filter(None, [c.get('firstName'), c.get('lastName')]))
                                    or c.get('name', '') for c in data.get('creators', [])],
                        'zotero_url': f'https://www.zotero.org/groups/{group_id}/items/{item_key}',
                        'collections': [], 'pdf_path': relative_path, 'sha256': file_hash(path),
                        'downloaded_at': datetime.now(timezone.utc).isoformat(),
                    }
                    if old:
                        manifest['papers'].remove(old)
                    manifest['papers'].append(paper)
                    existing[paper_id] = paper
                except Exception as error:
                    manifest['skipped'].append({'item_key': item_key, 'collection': name,
                                                'reason': str(error)})
                    emit(f'  Skipped {item_key}: {error}')
                    write_json(manifest_path, manifest)
                    continue
            if name not in paper['collections']:
                paper['collections'].append(name)
            chosen.append(item_key)
            write_json(manifest_path, manifest)
            emit(f'  [{len(chosen)}/{settings.count}] {item_key}: PDF ready')
        summary = {'name': name, 'key': key, 'candidates': len(candidates),
                   'requested': settings.count, 'downloaded': len(chosen)}
        manifest['collections'] = [c for c in manifest['collections'] if c['key'] != key] + [summary]
        write_json(manifest_path, manifest)
    manifest['complete'] = all(c['downloaded'] == settings.count for c in manifest['collections'])
    manifest['updated_at'] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    emit(f'{len(manifest["papers"])} unique PDFs ready; manifest: {manifest_path}')
    return manifest
