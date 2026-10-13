import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import observer, server


class ObserverTests(unittest.TestCase):
    def test_observer_preserves_original_csv_and_counts_each_model_call_once(self):
        import langchain_community.chat_models as models
        import langchain_community.document_loaders as loaders
        from langchain_core.documents import Document
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda
        import os
        import runpy

        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outputs = []
            for monitored in (False, True):
                directory = base / str(monitored)
                (directory / 'foldersam').mkdir(parents=True)
                (directory / 'foldersam' / 'fixture.pdf').write_bytes(b'%PDF-test-transport-fixture')
                observer.save(directory / 'state.json', dict(papers=[{'paper_id': 'fixture', 'pdf_path': 'fixture.pdf', 'status': 'queued'}], processed=0, accepted=0, status='starting'))
                # Deterministic transport fixtures only: original prompts, splitter,
                # chain, parser, selection and CSV writer execute unchanged.
                model = RunnableLambda(lambda _: AIMessage(content='{"device_type":"TOPCon","efficiency_percent":"24.8"}'))
                loader = SimpleNamespace(load=lambda: [Document(page_content='A controlled paper transport fixture.')])
                try:
                    with patch.object(models, 'ChatOllama', return_value=model), patch.object(loaders, 'PDFMinerLoader', return_value=loader), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        if monitored:
                            self.assertEqual(observer.run(directory), 0)
                        else:
                            os.chdir(directory)
                            runpy.run_path(str(observer.SOURCE), run_name='__main__')
                    outputs.append((directory / server.CSV_NAME).read_bytes())
                    if monitored:
                        state = json.loads((directory / 'state.json').read_text())
                        self.assertEqual(state['status'], 'completed')
                        self.assertEqual(state['papers'][0]['chunk'], 1)
                        self.assertEqual(state['papers'][0]['chunks'], 1)
                        self.assertEqual(state['papers'][0]['row_index'], 0)
                        self.assertEqual(state['accepted'], 1)
                finally:
                    os.chdir(previous)
            self.assertEqual(outputs[0], outputs[1])

    def test_original_entry_point_without_papers_preserves_source(self):
        source_hash = hashlib.sha256(observer.SOURCE.read_bytes()).hexdigest()
        previous = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                observer.save(directory / 'state.json', dict(papers=[], processed=0, accepted=0, status='starting'))
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = observer.run(directory)
                state = json.loads((directory / 'state.json').read_text())
                self.assertEqual(result, 0)
                self.assertEqual(state['status'], 'no_results')
                self.assertEqual(len(state['columns']), 27)
                self.assertEqual(state['source_sha256'], source_hash)
                self.assertFalse((directory / server.CSV_NAME).exists())
        finally:
            import os
            os.chdir(previous)
        self.assertEqual(hashlib.sha256(observer.SOURCE.read_bytes()).hexdigest(), source_hash)

    def test_skipped_paper_does_not_claim_another_papers_csv_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            observer.save(directory / 'state.json', dict(papers=[{}, {}], processed=0, accepted=0))
            monitor = observer.Observer(directory)
            monitor.column_map = {'device_type': 'Device Type'}
            monitor.current = 0
            monitor.finish_paper([])
            monitor.current = 1
            monitor.finish_paper([{'device_type': 'TOPCon'}])
            self.assertEqual(monitor.state['papers'][0]['status'], 'no_result')
            self.assertNotIn('row_index', monitor.state['papers'][0])
            self.assertEqual(monitor.state['papers'][1]['row_index'], 0)
            self.assertEqual(monitor.state['papers'][1]['values'], {'Device Type': 'TOPCon'})


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.runs_patch = patch.object(server, 'RUNS', self.directory / 'runs')
        self.settings_patch = patch.object(server.Settings, 'load', return_value=SimpleNamespace(pdf_dir=self.directory))
        self.runs_patch.start()
        self.settings_patch.start()
        self.jobs = server.Jobs()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.handler(self.jobs))
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.runs_patch.stop()
        self.settings_patch.stop()
        self.temporary.cleanup()

    def test_csv_download_is_exact_original_bytes_and_quoted_values_are_read(self):
        self.jobs.directory = self.directory / 'runs' / 'test'
        self.jobs.directory.mkdir()
        observer.save(self.jobs.directory / 'state.json', dict(status='completed', papers=[], processed=0, accepted=1, columns=[]))
        data = b'Device Type,Key Findings\r\nTOPCon,"Quoted, exact value"\r\n'
        (self.jobs.directory / server.CSV_NAME).write_bytes(data)
        with urlopen(self.url + '/api/csv') as response:
            self.assertEqual(response.read(), data)
        snapshot = self.jobs.snapshot()
        self.assertEqual(snapshot['rows'], [{'Device Type': 'TOPCon', 'Key Findings': 'Quoted, exact value'}])

    def test_cross_origin_start_is_rejected(self):
        request = Request(self.url + '/api/start', data=b'{}', headers={'Origin': 'https://other.example', 'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 403)
        self.assertIsNone(self.jobs.process)

    def test_manifest_cannot_escape_pdf_folder(self):
        self.jobs.pdf_dir = self.directory / 'pdf'
        self.jobs.pdf_dir.mkdir()
        (self.directory / 'private.pdf').write_bytes(b'%PDF-outside-the-corpus')
        (self.jobs.pdf_dir / 'manifest.json').write_text(json.dumps({'papers': [{'pdf_path': '../private.pdf', 'paper_id': 'outside'}]}))
        self.assertEqual(self.jobs.corpus(), [])


if __name__ == '__main__':
    unittest.main()
