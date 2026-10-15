import contextlib
import csv
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
from dashboard import observer, server, structured_worker
import extract_csv


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
        self.jobs = server.Jobs(database=self.directory / "test.sqlite3")
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

    def test_sqlite_history_individual_download_and_missing_export_survive_restart(self):
        (self.directory / 'paper.pdf').write_bytes(b'%PDF-fixture')
        (self.directory / 'manifest.json').write_text(json.dumps({'papers':[
            dict(paper_id='paper',title='Paper',pdf_path='paper.pdf',authors=[],collections=['Si-PERC'])]}))
        row = dict.fromkeys(extract_csv.COLUMN_MAP.values(),'N/A')
        row.update({'Source PDF':'paper.pdf','Status':'partial','Title':'Paper','Model':'gemma3:1b',
                    'Filled Fields':'1','Device Type':'PERC','Chunks Processed':'3'})
        source = self.directory / 'saved.csv'
        from extraction_store import csv_bytes
        source.write_bytes(csv_bytes([row]))
        snapshot = self.jobs.import_csv(source)
        run_id = snapshot['run_id']
        with urlopen(self.url+'/api/runs') as response:
            history = json.load(response)['runs']
        self.assertEqual(history[0]['run_id'],run_id)
        with urlopen(self.url+f'/api/csv?run_id={run_id}&paper_id=paper') as response:
            decoded = list(csv.DictReader(io.StringIO(response.read().decode('utf-8-sig'))))
        self.assertEqual(decoded[0]['Device Type'],'PERC')
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.url+f'/api/csv?run_id={run_id}&paper_id=missing')
        self.assertEqual(caught.exception.code,404)
        export = self.jobs.csv_path(snapshot)
        expected = export.read_bytes()
        export.unlink()
        restored = server.Jobs(database=self.directory/'test.sqlite3')
        self.assertEqual(restored.snapshot(run_id)['rows'],snapshot['rows'])
        self.assertEqual(export.read_bytes(),expected)
        self.assertFalse(restored.snapshot(run_id)['can_resume'])
        self.assertFalse(restored.snapshot(run_id)['can_retry'])
        with self.assertRaisesRegex(ValueError,'Imported CSV'):
            restored.resume(run_id)

    def test_resume_action_rejects_missing_run_and_cross_origin(self):
        request = Request(self.url+'/api/resume',data=b'{}',
                          headers={'Origin':self.url,'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code,409)
        request = Request(self.url+'/api/retry-failed',data=b'{"run_id":"x"}',
                          headers={'Origin':'https://other.example','Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code,403)

    def test_import_bom_csv_matches_source_paper_and_retains_partial_status(self):
        papers = []
        for name in ('processed', 'unprocessed'):
            (self.directory / f'{name}.pdf').write_bytes(b'%PDF-fixture')
            papers.append(dict(paper_id=name, title=name, pdf_path=f'{name}.pdf',
                               authors=[], collections=['Si-PERC']))
        (self.directory / 'manifest.json').write_text(json.dumps({'papers': papers}))
        source = self.directory / 'sample.csv'
        row = dict.fromkeys(extract_csv.COLUMN_MAP.values(), 'N/A')
        row.update({'Source PDF': 'processed.pdf', 'Status': 'partial',
                    'Title': 'Processed paper', 'Model': 'gemma3:1b',
                    'Chunks Processed': '15', 'Selected Chunk': '3',
                    'Filled Fields': '1', 'Device Type': 'PERC', 'Error': 'A chunk failed.'})
        with source.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        snapshot = self.jobs.import_csv(source)
        self.assertEqual(snapshot['status'], 'completed_with_issues')
        self.assertEqual(snapshot['run_total'], 1)
        self.assertEqual(snapshot['processed'], 1)
        self.assertEqual(snapshot['corpus_count'], 2)
        self.assertEqual(len(snapshot['field_columns']), 27)
        self.assertTrue(snapshot['csv_available'])
        by_id = {paper['paper_id']: paper for paper in snapshot['papers']}
        self.assertEqual(by_id['processed']['row_index'], 0)
        self.assertEqual(by_id['processed']['status'], 'partial')
        self.assertEqual(by_id['processed']['selected_chunk'], 3)
        self.assertEqual(by_id['unprocessed']['status'], 'not_run')
        self.assertNotIn('row_index', by_id['unprocessed'])
        self.assertNotIn('\ufeffSource PDF', snapshot['columns'])
        with urlopen(self.url + '/api/csv') as response:
            self.assertEqual(response.read(), source.read_bytes())
            self.assertIn(server.STRUCTURED_CSV_NAME, response.headers['Content-Disposition'])
        restored = server.Jobs(database=self.directory / "test.sqlite3").snapshot()
        self.assertEqual(restored['rows'], snapshot['rows'])

    def test_structured_saved_rows_remain_downloadable_after_stop(self):
        self.jobs.directory = self.directory / 'runs' / 'stopped'
        self.jobs.directory.mkdir()
        observer.save(self.jobs.directory / 'state.json', dict(status='stopped', extractor='structured',
                      csv_name=server.STRUCTURED_CSV_NAME, papers=[], processed=1, accepted=0, columns=[]))
        data = b'Source PDF,Status\r\nfixture.pdf,no_data\r\n'
        (self.jobs.directory / server.STRUCTURED_CSV_NAME).write_bytes(data)
        with urlopen(self.url + '/api/csv') as response:
            self.assertEqual(response.read(), data)

    def test_structured_worker_publishes_real_csv_and_progress(self):
        directory = self.directory / 'worker'
        (directory / 'foldersam').mkdir(parents=True)
        (directory / 'foldersam' / 'fixture.pdf').write_bytes(b'%PDF-transport-fixture')
        paper = dict(paper_id='fixture', pdf_path='fixture.pdf', title='Fixture',
                     status='queued', chunk=0, chunks=0)
        from extraction_runtime import DEFAULTS, create_run
        from extraction_store import Store
        from types import SimpleNamespace
        store = Store(self.directory / 'worker.sqlite3')
        args = SimpleNamespace(**DEFAULTS,output=directory / server.STRUCTURED_CSV_NAME)
        paper.update(path=directory / 'foldersam' / 'fixture.pdf')
        state = create_run(store,[paper],args,'fixture-digest',run_id='worker-test',directory=directory)
        state['database'] = str(store.path)
        store.save_state(state)
        observer.save(directory / 'state.json',state)
        content = dict.fromkeys(extract_csv.RESPONSE_FIELDS, 'N/A')
        content.update(device_type='TOPCon', efficiency_percent='25.1',
                       cell_evidence='Our cell efficiency was 25.1%.')
        def reply(url,payload,timeout):
            keys = payload['format']['required']
            values = {key: ('E1' if key=='evidence_id' else content[key]) for key in keys}
            return dict(done=True,done_reason='stop',message={'content':json.dumps(values)})
        with patch('extraction_runtime.model_digest',return_value='fixture-digest'), \
                patch.object(extract_csv,'extract_text',return_value=content['cell_evidence']), \
                patch('focused_extraction.ollama_chat',side_effect=reply), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(structured_worker.work(directory),0)
        state = store.load('worker-test')['state']
        self.assertEqual(state['status'],'completed')
        self.assertEqual(state['processed'],1)
        self.assertEqual(state['accepted'],1)
        rows = store.rows('worker-test')
        self.assertEqual(rows[0]['Device Type'],'TOPCon')
        self.assertEqual(rows[0]['Efficiency (%)'],'25.1')
        self.assertEqual((directory / server.STRUCTURED_CSV_NAME).read_bytes(),store.artifact('worker-test'))
        self.assertEqual(len(list((directory / 'papers').glob('*.csv'))),1)
        self.assertTrue((directory / 'pv_extraction_results.responses.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
