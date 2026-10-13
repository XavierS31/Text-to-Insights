import ast
import contextlib
import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extract_csv


class ExtractionTests(unittest.TestCase):
    def test_schema_echo_null_and_malformed_json_are_rejected(self):
        for content in ('null', '{"properties": {}}', '{"device_type":"TOPCon"}}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                extract_csv.validate_content(content)
        data = dict.fromkeys(extract_csv.RESPONSE_FIELDS, 'N/A')
        data['efficiency_percent'] = None
        with self.assertRaises(ValueError):
            extract_csv.validate_content(json.dumps(data))

    def test_fields_match_sponsor_and_chunks_preserve_text(self):
        source = Path(__file__).resolve().parents[1] / 'PV-Work/mainScript/extraction.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        original = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                        if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == 'COLUMN_MAP'
                                for target in node.targets))
        self.assertEqual(extract_csv.COLUMN_MAP, original)
        text = 'x' * 2100
        chunks = extract_csv.split_text(text, size=500, overlap=20)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))
        self.assertEqual(chunks[0] + ''.join(chunk[20:] for chunk in chunks[1:]), text)
        # Paragraph boundaries must never move the cursor backwards with large overlap.
        chunks = extract_csv.split_text(('x' * 100 + '\n') * 12, size=500, overlap=450)
        self.assertLess(len(chunks), 30)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))

    def test_highest_efficiency_beats_more_filled_fields(self):
        best_efficiency = dict.fromkeys(extract_csv.COLUMN_MAP, 'N/A')
        best_efficiency['efficiency_percent'] = '25.1%'
        more_complete = dict.fromkeys(extract_csv.COLUMN_MAP, 'some value')
        more_complete['efficiency_percent'] = '22.0'
        self.assertGreater(extract_csv.candidate_score(best_efficiency),
                           extract_csv.candidate_score(more_complete))

    def test_invented_performance_and_quotes_are_rejected(self):
        data = dict.fromkeys(extract_csv.RESPONSE_FIELDS, 'N/A')
        data.update(efficiency_percent='98.7', cell_evidence='The cell efficiency is 98.7%.')
        with self.assertRaisesRegex(ValueError, 'exact quote'):
            extract_csv.validate_grounding(data, 'The cell efficiency is 20.1%.')
        data.update(efficiency_percent='20.1', cell_evidence='The cell efficiency is 20.1%.')
        extract_csv.validate_grounding(data, 'The cell efficiency is 20.1%.')
        data['open_circuit_voltage_v'] = '1.3'
        with self.assertRaisesRegex(ValueError, 'absent'):
            extract_csv.validate_grounding(data, 'The cell efficiency is 20.1%.')
        data['open_circuit_voltage_v'] = 'N/A'
        data['cell_evidence'] = 'The cell efficiency is 120.15%.'
        with self.assertRaisesRegex(ValueError, 'absent'):
            extract_csv.validate_grounding(data, data['cell_evidence'])

    def test_http_retry_csv_failure_rows_and_raw_provenance(self):
        requests = []
        data = dict.fromkeys(extract_csv.RESPONSE_FIELDS, 'N/A')
        data.update(device_type='TOPCon', key_findings='Quoted, "value"', efficiency_percent='25.1')
        data['cell_evidence'] = 'The TOPCon cell reached 25.1% efficiency.'
        replies = ['null', json.dumps(data), json.dumps(dict.fromkeys(data, 'N/A')),
                   '{"properties":{}}', '{"properties":{}}']

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                payload = json.dumps({'done': True, 'done_reason': 'stop',
                                      'message': {'content': replies.pop(0)}}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                for name in ('a', 'b', 'c', 'd'):
                    (directory / f'{name}.pdf').write_bytes(b'%PDF-transport-fixture')
                args = SimpleNamespace(pdf_dir=directory, output=directory / 'results.csv',
                                       limit=None, model='fixture', retries=1, timeout=5,
                                       ollama_url=f'http://127.0.0.1:{http.server_port}',
                                       chunk_size=4000, chunk_overlap=200, context_size=8192)
                with patch.object(extract_csv, 'extract_text', side_effect=[data['cell_evidence'], 'paper B', 'paper C', '']), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(extract_csv.run(args), 2)
                with args.output.open(encoding='utf-8-sig', newline='') as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([row['Status'] for row in rows],
                                 ['extracted', 'no_data', 'failed', 'no_text'])
                self.assertEqual(rows[0]['Key Findings'], 'Quoted, "value"')
                self.assertEqual(rows[0]['Selected Chunk'], '1')
                self.assertIn('Chunk 1, attempt 1', rows[0]['Error'])
                self.assertEqual(rows[2]['Efficiency (%)'], 'N/A')
                self.assertEqual(rows[2]['Filled Fields'], '0')
                records = [json.loads(line) for line in args.output.with_suffix('.responses.jsonl').read_text().splitlines()]
                self.assertEqual(len(records), 5)
                self.assertEqual(records[0]['response']['message']['content'], 'null')
                self.assertEqual(records[1]['source_pdf'], 'a.pdf')
                self.assertEqual(records[1]['attempt'], 2)
                self.assertEqual(requests[0]['format'], extract_csv.chunk_schema(data['cell_evidence']))
                self.assertFalse(requests[0]['stream'])
                with self.assertRaises(FileExistsError):
                    extract_csv.run(args)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_partial_row_keeps_values_when_another_chunk_fails(self):
        data = dict.fromkeys(extract_csv.RESPONSE_FIELDS, 'N/A')
        data.update(device_type='TOPCon', efficiency_percent='24.5')
        args = SimpleNamespace(chunk_size=500, chunk_overlap=0)
        paper = dict(path=Path('fixture.pdf'), pdf_path='fixture.pdf', title='Fixture')
        with patch.object(extract_csv, 'extract_text', return_value='x' * 600), \
                patch.object(extract_csv, 'extract_chunk', side_effect=[(data, []), (None, ['invalid JSON'])]), \
                contextlib.redirect_stdout(io.StringIO()):
            row = extract_csv.extract_paper(paper, args=SimpleNamespace(**vars(args), model='fixture'), raw_log=io.StringIO())
        self.assertEqual(row['Status'], 'partial')
        self.assertEqual(row['Efficiency (%)'], '24.5')
        self.assertEqual(row['Selected Chunk'], 1)
        self.assertIn('invalid JSON', row['Error'])

    def test_evidence_schema_allows_only_literal_efficiency_windows(self):
        text = 'Our cell reached an efficiency of 20.9%. The voltage was 0.66 V.'
        schema = extract_csv.chunk_schema(text)
        self.assertEqual(schema['properties']['cell_evidence']['enum'], ['N/A', text])
        no_performance = extract_csv.chunk_schema('Laser stripes are 85 microns wide.')
        for key in extract_csv.PERFORMANCE_FIELDS:
            self.assertEqual(no_performance['properties'][key]['enum'], ['N/A'])


if __name__ == '__main__':
    unittest.main()
