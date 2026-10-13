"""Zotero client deliberately exposing GET requests only.

Credentials never follow attachment redirects to storage or publisher hosts.
"""
import time
from urllib.parse import urlparse

import requests


class ZoteroReader:
    base_url = 'https://api.zotero.org'

    def __init__(self, api_key):
        if not api_key:
            raise ValueError('ZOTERO_API_KEY is missing. Copy .env.example to .env and set the key.')
        self._key = api_key
        self._session = requests.Session()
        self._next_request = 0.0

    def get(self, path, *, params=None, stream=False):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Only Zotero API paths are accepted.')
        for attempt in range(4):
            delay = self._next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            response = self._session.get(
                self.base_url + path, params=params, stream=stream,
                headers={'Zotero-API-Key': self._key, 'Zotero-API-Version': '3'},
                allow_redirects=False, timeout=(15, 90),
            )
            wait = response.headers.get('Backoff', response.headers.get('Retry-After', '0'))
            try:
                self._next_request = time.monotonic() + float(wait)
            except ValueError:
                self._next_request = time.monotonic() + 10
            if response.status_code == 429 or response.status_code >= 500:
                response.close()
                if attempt < 3:
                    self._next_request = max(self._next_request, time.monotonic() + 2 ** attempt)
                    continue
            response.raise_for_status()
            return response
        raise RuntimeError('Zotero request failed after retries.')

    def json(self, path):
        with self.get(path) as response:
            return response.json()

    def all(self, path, **params):
        start = 0
        items = []
        while True:
            with self.get(path, params={**params, 'limit': 100, 'start': start}) as response:
                page = response.json()
                items.extend(page)
                total = int(response.headers.get('Total-Results', start + len(page)))
            start += len(page)
            if not page or start >= total:
                return items

    def resolve_group(self, name, configured_id=''):
        if configured_id:
            group = self.json(f'/groups/{int(configured_id)}')
            if group['data']['name'].casefold() != name.casefold():
                raise ValueError('Configured group ID does not match ZOTERO_GROUP_NAME.')
            return str(group['id'])
        user_id = self.json('/keys/current')['userID']
        groups = self.all(f'/users/{user_id}/groups')
        matches = [g for g in groups if g['data']['name'].casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError(f'Could not uniquely find group {name!r}; set ZOTERO_GROUP_ID.')
        return str(matches[0]['id'])

    def download_pdf(self, group_id, attachment_key, target):
        response = self.get(f'/groups/{group_id}/items/{attachment_key}/file', stream=True)
        try:
            if response.is_redirect:
                location = response.headers['Location']
                parsed = urlparse(location)
                if parsed.scheme != 'https' or not parsed.netloc:
                    raise ValueError('Attachment storage redirect must use HTTPS.')
                response.close()
                # New unauthenticated request: never forward the Zotero key.
                response = requests.get(location, stream=True, timeout=(15, 90))
                response.raise_for_status()
            temporary = target.with_suffix('.pdf.part')
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with temporary.open('wb') as output:
                    for chunk in response.iter_content(1024 * 1024):
                        output.write(chunk)
                with temporary.open('rb') as downloaded:
                    if b'%PDF-' not in downloaded.read(1024):
                        raise ValueError('Downloaded attachment is not a PDF.')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        finally:
            response.close()
