"""Failure, recovery and durable storage contracts, independent of live model accuracy."""
import contextlib
import csv
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import extract_csv
import focused_extraction as focused
import extraction_runtime as runtime
from extraction_store import Store, WorkerLock, csv_bytes


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'a.pdf'
        self.pdf.write_bytes(b'%PDF-fixture')
        self.paper = dict(paper_id='a',pdf_path='a.pdf',path=self.pdf,title='Paper A',collections=['Si-PERC'])
        self.args = SimpleNamespace(**runtime.DEFAULTS,pdf_dir=self.root,output=self.root / 'run/results.csv',
                                    database=self.root / 'db.sqlite3',limit=None)
        self.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def reply(self,url,payload,timeout):
        self.calls.append(payload)
        keys = payload['format']['required']
        data = dict.fromkeys(keys,'N/A')
        if 'device_type' in keys:
            data['device_type'] = 'PERC'
        return dict(done=True,done_reason='stop',message=dict(content=json.dumps(data)))

    def execute(self,**kwargs):
        with patch.object(runtime,'model_digest',return_value='digest'), \
             patch.object(extract_csv,'extract_text',return_value='The authors fabricated PERC cells.'), \
             patch.object(focused,'ollama_chat',side_effect=kwargs.get('reply',self.reply)), \
             contextlib.redirect_stdout(io.StringIO()):
            return extract_csv.run(self.args,papers=[self.paper])

    def test_truncation_splits_to_single_fields_and_checkpoints_survive_resume(self):
        def reply(url,payload,timeout):
            if len(payload['format']['required']) > 1:
                self.calls.append(payload)
                return dict(done=True,done_reason='length',message={'content':'{}'})
            return self.reply(url,payload,timeout)
        self.assertEqual(self.execute(reply=reply),0)
        store = Store(self.args.database)
        row = store.rows(self.args.run_id)[0]
        self.assertEqual(row['Device Type'],'PERC')
        self.assertEqual(row['Status'],'extracted')
        self.assertIn('output_limit',row['Error'])
        self.assertLess(len(self.calls),100)
        for payload in self.calls:
            self.assertEqual(payload['model'],'gemma3:1b')
            self.assertEqual(payload['options'],dict(temperature=0,num_ctx=8192,num_predict=1024))
        self.assertEqual(len(row),38)
        self.assertEqual(store.artifact(self.args.run_id),self.args.output.read_bytes())

    def test_interruption_reuses_only_committed_tasks_and_fresh_run_calls_again(self):
        def offline(url,payload,timeout):
            if len(self.calls)==2:
                raise URLError('connection refused')
            return self.reply(url,payload,timeout)
        self.assertEqual(self.execute(reply=offline),3)
        first_id = self.args.run_id
        first_tasks = [p['format']['required'] for p in self.calls]
        store = Store(self.args.database)
        self.assertEqual(store.load(first_id)['state']['status'],'interrupted')
        self.assertEqual(store.rows(first_id),[])
        self.args.resume_existing = True
        self.assertEqual(self.execute(),0)
        for fields in first_tasks:
            self.assertEqual(sum(p['format']['required']==fields for p in self.calls),1)
        self.assertEqual(len(store.rows(first_id)),1)
        resumed_count = len(self.calls)
        self.args = SimpleNamespace(**runtime.DEFAULTS,pdf_dir=self.root,output=self.root / 'fresh/results.csv',
                                    database=self.root / 'db.sqlite3',limit=None)
        self.assertEqual(self.execute(),0)
        self.assertNotEqual(first_id,self.args.run_id)
        self.assertGreater(len(self.calls),resumed_count)

    def test_failed_tasks_stay_failed_until_explicit_retry_and_completed_rows_not_duplicated(self):
        def invalid(url,payload,timeout):
            self.calls.append(payload)
            return dict(done=True,done_reason='stop',message=dict(content='null'))
        self.assertEqual(self.execute(reply=invalid),2)
        store = Store(self.args.database)
        self.assertEqual(store.rows(self.args.run_id)[0]['Status'],'failed')
        self.args.resume_existing = True
        self.args.retry_failed = True
        self.assertEqual(self.execute(),0)
        self.assertEqual(len(store.rows(self.args.run_id)),1)
        self.assertEqual(store.rows(self.args.run_id)[0]['Status'],'extracted')
        with store.connect() as db:
            self.assertGreater(db.execute('SELECT count(*) FROM attempts').fetchone()[0],len(focused.GROUPS))

    def test_resume_refuses_changed_pdf_settings_and_model(self):
        self.assertEqual(self.execute(),0)
        self.args.resume_existing = True
        self.args.chunk_size += 1
        with self.assertRaisesRegex(ValueError,'settings changed'):
            self.execute()
        self.args.chunk_size -= 1
        with patch.object(runtime,'model_digest',return_value='new-digest'),self.assertRaisesRegex(ValueError,'digest changed'):
            runtime.validate_resume(Store(self.args.database),self.args.run_id)
        self.pdf.write_bytes(b'%PDF-changed')
        with self.assertRaisesRegex(ValueError,'PDF changed'):
            self.execute()

    def test_result_and_csv_transaction_rolls_back_together_and_exports_regenerate(self):
        self.assertEqual(self.execute(),0)
        store = Store(self.args.database)
        original = store.artifact(self.args.run_id)
        row = dict(store.rows(self.args.run_id)[0], **{'Device Type':'changed'})
        with patch('extraction_store.csv_bytes',side_effect=[csv_bytes([row]),RuntimeError('interrupted publication')]):
            with self.assertRaises(RuntimeError):
                store.save_result(self.args.run_id,'a',row)
        self.assertEqual(store.artifact(self.args.run_id),original)
        self.assertEqual(store.rows(self.args.run_id)[0]['Device Type'],'PERC')
        self.args.output.unlink()
        store.export(self.args.run_id,self.args.output)
        self.assertEqual(self.args.output.read_bytes(),original)
        paper_csv = store.artifact(self.args.run_id,'a')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(paper_csv.decode('utf-8-sig'))))),1)
        with store.connect() as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
            scientific = [r[1] for r in db.execute('PRAGMA table_info(results)') if r[1] in extract_csv.COLUMN_MAP]
            self.assertEqual(scientific,list(extract_csv.COLUMN_MAP))

    def test_worker_lock_prevents_another_worker(self):
        with WorkerLock(self.args.database):
            with self.assertRaisesRegex(ValueError,'already running'):
                with WorkerLock(self.args.database):
                    self.fail('second worker acquired lock')

    def test_crash_after_successful_attempt_commit_does_not_repeat_request(self):
        original = Store.save_attempt
        crashed = False
        def commit_then_crash(store,run_id,paper_id,key,record,data=None,errors=None):
            nonlocal crashed
            original(store,run_id,paper_id,key,record,data,errors)
            if data is not None and not crashed:
                crashed = True
                raise KeyboardInterrupt()
        with patch.object(Store,'save_attempt',new=commit_then_crash):
            self.assertEqual(self.execute(),3)
        first_fields = self.calls[0]['format']['required']
        self.args.resume_existing = True
        self.assertEqual(self.execute(),0)
        self.assertEqual(sum(p['format']['required']==first_fields for p in self.calls),1)

    def test_parallel_reads_and_export_repair_do_not_conflict_with_writer(self):
        from concurrent.futures import ThreadPoolExecutor
        self.assertEqual(self.execute(),0)
        store = Store(self.args.database)
        def reader():
            for _ in range(8):
                store.export(self.args.run_id,self.args.output)
                self.assertEqual(len(store.rows(self.args.run_id)),1)
        def writer():
            for i in range(15):
                store.save_task(self.args.run_id,'a',str(i),{'test':'value'},[])
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = [pool.submit(reader),pool.submit(reader),pool.submit(writer)]
            for job in jobs:
                job.result()
        self.assertEqual(self.args.output.read_bytes(),store.artifact(self.args.run_id))

    def test_fake_evidence_and_repetition_are_rejected_without_silent_na(self):
        def repetition(url,payload,timeout):
            from urllib.error import HTTPError
            raise HTTPError(url,500,'repeat',{},io.BytesIO(b'prediction aborted, token repeat limit reached'))
        with patch.object(focused,'ollama_chat',side_effect=repetition),contextlib.redirect_stdout(io.StringIO()):
            data,errors = focused.extract('An efficiency of 25.0% was measured.',1,self.paper,self.args,io.StringIO())
        self.assertIsNone(data)
        self.assertEqual(len(errors),2)
        self.assertTrue(all('repetition' in message for message in errors))
        def fake(url,payload,timeout):
            return dict(done=True,done_reason='stop',message={'content':json.dumps({'evidence_id':'E999','efficiency_percent':'25.0'})})
        with patch.object(focused,'ollama_chat',side_effect=fake),contextlib.redirect_stdout(io.StringIO()):
            data,errors = focused.extract('An efficiency of 25.0% was measured.',1,self.paper,self.args,io.StringIO())
        self.assertIsNone(data)
        self.assertTrue(all('unknown evidence ID' in message for message in errors))

    def test_timeout_retries_and_measurements_require_selected_window(self):
        count = 0
        def timeout_once(url,payload,timeout):
            nonlocal count
            count += 1
            if count == 1:
                raise TimeoutError('request exceeded timeout')
            return self.reply(url,payload,timeout)
        self.assertEqual(self.execute(reply=timeout_once),0)
        self.assertIn('timeout',Store(self.args.database).rows(self.args.run_id)[0]['Error'])


if __name__ == '__main__':
    unittest.main()
