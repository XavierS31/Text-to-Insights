"""Durable local runs, request checkpoints and exact CSV artifacts."""
from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

DEFAULT_DB = Path(__file__).resolve().parents[1] / '.extraction-runs/extractions.sqlite3'
VERSION = 'grouped-v1'
TERMINAL = ('extracted', 'partial', 'no_data', 'partial_no_data', 'no_text', 'failed')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def csv_bytes(rows, columns=None):
    from extract_csv import META_COLUMNS, COLUMN_MAP
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=columns or META_COLUMNS + list(COLUMN_MAP.values()),
                            extrasaction='ignore', lineterminator='\r\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


class WorkerLock:
    """An OS lock survives server restarts and is released on worker termination."""
    def __init__(self, database):
        self.path = Path(database).with_suffix('.worker.lock')
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        self.handle.seek(0)
        if self.path.stat().st_size == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            raise ValueError('An extraction worker is already running. Stop it before starting another.') from error
        return self

    def __exit__(self, *args):
        self.handle.close()


class Store:
    def __init__(self, path=DEFAULT_DB):
        from extract_csv import COLUMN_MAP
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fields = COLUMN_MAP
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            fields = ','.join(f'"{key}" TEXT NOT NULL' for key in COLUMN_MAP)
            db.executescript(f'''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, created REAL NOT NULL, state TEXT NOT NULL,
                    config TEXT NOT NULL, digest TEXT NOT NULL, imported INTEGER NOT NULL DEFAULT 0,
                    worker_pid INTEGER, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS papers (
                    run_id TEXT NOT NULL REFERENCES runs(run_id), paper_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, pdf_hash TEXT NOT NULL, source TEXT NOT NULL,
                    PRIMARY KEY(run_id,paper_id));
                CREATE TABLE IF NOT EXISTS results (
                    run_id TEXT NOT NULL, paper_id TEXT NOT NULL, metadata TEXT NOT NULL,
                    row_json TEXT NOT NULL, csv BLOB NOT NULL, {fields},
                    PRIMARY KEY(run_id,paper_id),
                    FOREIGN KEY(run_id,paper_id) REFERENCES papers(run_id,paper_id));
                CREATE TABLE IF NOT EXISTS tasks (
                    run_id TEXT NOT NULL, paper_id TEXT NOT NULL, task_key TEXT NOT NULL,
                    status TEXT NOT NULL, data TEXT, errors TEXT NOT NULL,
                    PRIMARY KEY(run_id,paper_id,task_key),
                    FOREIGN KEY(run_id,paper_id) REFERENCES papers(run_id,paper_id));
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, paper_id TEXT NOT NULL,
                    task_key TEXT NOT NULL, recorded REAL NOT NULL, record TEXT NOT NULL,
                    FOREIGN KEY(run_id,paper_id) REFERENCES papers(run_id,paper_id));
                CREATE INDEX IF NOT EXISTS attempts_run ON attempts(run_id,paper_id);
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id), csv BLOB NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, state, papers, config, digest='', imported=False):
        sources = [(p, file_hash(p['path']) if p.get('path') else '') for p in papers]
        with self.connect() as db:
            db.execute('INSERT INTO runs(run_id,created,state,config,digest,imported) VALUES(?,?,?,?,?,?)',
                       (state['run_id'], time.time(), json.dumps(state), json.dumps(config), digest, imported))
            for ordinal, (paper, sha) in enumerate(sources):
                source = {k: str(v) if isinstance(v, Path) else v for k, v in paper.items()}
                db.execute('INSERT INTO papers VALUES(?,?,?,?,?)',
                           (state['run_id'], paper['paper_id'], ordinal, sha, json.dumps(source)))

    def exists(self, run_id):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone() is not None

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                raise ValueError('Saved run not found.')
            return dict(state=json.loads(row['state']), config=json.loads(row['config']),
                        digest=row['digest'], imported=bool(row['imported']), worker_pid=row['worker_pid'])

    def save_state(self, state, worker_pid=None):
        with self.connect() as db:
            db.execute('UPDATE runs SET state=?,worker_pid=?,revision=revision+1 WHERE run_id=?',
                       (json.dumps(state, ensure_ascii=False), worker_pid, state['run_id']))

    def set_worker(self, run_id, pid):
        with self.connect() as db:
            db.execute('UPDATE runs SET worker_pid=? WHERE run_id=?',(pid,run_id))

    def active(self):
        with self.connect() as db:
            rows = db.execute('SELECT run_id,state,worker_pid FROM runs ORDER BY created DESC').fetchall()
        for row in rows:
            state = json.loads(row['state'])
            if state.get('status') in ('starting', 'running'):
                if pid_alive(row['worker_pid']):
                    return row['run_id'], row['worker_pid']
                # Reserve the brief interval between job creation and worker startup.
                if state.get('status') == 'starting' and time.time() - state.get('updated_at', 0) < 15:
                    return row['run_id'], None
        return None

    def history(self):
        with self.connect() as db:
            rows = db.execute('SELECT state FROM runs ORDER BY created DESC').fetchall()
        return [{k: s.get(k) for k in ('run_id','status','started_at','finished_at','processed','run_total','imported')}
                for s in (json.loads(row['state']) for row in rows)]

    def sources(self, run_id):
        with self.connect() as db:
            return [dict(json.loads(r['source']), pdf_hash=r['pdf_hash']) for r in
                    db.execute('SELECT * FROM papers WHERE run_id=? ORDER BY ordinal', (run_id,))]

    def rows(self, run_id):
        with self.connect() as db:
            return [json.loads(r['row_json']) for r in db.execute('''SELECT r.row_json FROM results r
                JOIN papers p USING(run_id,paper_id) WHERE r.run_id=? ORDER BY p.ordinal''', (run_id,))]

    def result(self, run_id, paper_id):
        with self.connect() as db:
            row = db.execute('SELECT row_json FROM results WHERE run_id=? AND paper_id=?', (run_id,paper_id)).fetchone()
            return json.loads(row[0]) if row else None

    def save_result(self, run_id, paper_id, row):
        from extract_csv import META_COLUMNS
        fields = list(self.fields)
        names = ','.join(f'"{key}"' for key in fields)
        values = [row.get(self.fields[key], 'N/A') for key in fields]
        with self.connect() as db:
            db.execute(f'INSERT OR REPLACE INTO results(run_id,paper_id,metadata,row_json,csv,{names}) '
                       f'VALUES({",".join("?" for _ in range(5+len(fields)))})',
                       [run_id,paper_id,json.dumps({k:row.get(k,'') for k in META_COLUMNS}),
                        json.dumps(row,ensure_ascii=False),csv_bytes([row]),*values])
            rows = [json.loads(r[0]) for r in db.execute('''SELECT r.row_json FROM results r
                JOIN papers p USING(run_id,paper_id) WHERE r.run_id=? ORDER BY p.ordinal''', (run_id,))]
            db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?)', (run_id,csv_bytes(rows)))

    def artifact(self, run_id, paper_id=None):
        with self.connect() as db:
            if paper_id is None:
                row = db.execute('SELECT csv FROM artifacts WHERE run_id=?', (run_id,)).fetchone()
            else:
                row = db.execute('SELECT csv FROM results WHERE run_id=? AND paper_id=?', (run_id,paper_id)).fetchone()
            return bytes(row[0]) if row else None

    def preserve_artifact(self, run_id, data):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?)', (run_id,data))

    def checkpoint(self, run_id, paper_id, key):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE run_id=? AND paper_id=? AND task_key=?',
                             (run_id,paper_id,key)).fetchone()
            return dict(status=row['status'], data=json.loads(row['data']) if row['data'] else None,
                        errors=json.loads(row['errors'])) if row else None

    def save_task(self, run_id, paper_id, key, data, errors):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?,?,?,?)',
                       (run_id,paper_id,key,'valid' if data is not None else 'failed',
                        json.dumps(data) if data is not None else None,json.dumps(errors)))

    def save_attempt(self, run_id, paper_id, key, record, data=None, errors=None):
        with self.connect() as db:
            db.execute('INSERT INTO attempts(run_id,paper_id,task_key,recorded,record) VALUES(?,?,?,?,?)',
                       (run_id,paper_id,key,time.time(),json.dumps(record,ensure_ascii=False)))
            if data is not None:
                # The successful response and its resumable checkpoint commit together.
                db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?,?,?,?,?)',
                           (run_id,paper_id,key,'valid',json.dumps(data),json.dumps(errors or [])))

    def clear_failed(self, run_id):
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE run_id=? AND status='failed'", (run_id,))

    def export(self, run_id, output):
        """Exports are replaceable views; committed SQLite artifacts remain authoritative."""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        data = self.artifact(run_id)
        if data is None:
            return
        def write(path, content):
            temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            temporary.write_bytes(content)
            for attempt in range(8):
                try:
                    temporary.replace(path)
                    return
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(.025)
        write(output, data)
        folder = output.parent / 'papers'
        folder.mkdir(exist_ok=True)
        for paper in self.sources(run_id):
            content = self.artifact(run_id, paper['paper_id'])
            if content:
                name = hashlib.sha256(paper['paper_id'].encode()).hexdigest()[:20] + '.csv'
                write(folder / name, content)
