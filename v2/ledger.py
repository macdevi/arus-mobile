"""V2 persistence. No live application import or automatic initialization."""
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from v2_core import exchange_rate

@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
    finally:
        db.close()

def initialize(db):
    root = Path(__file__).parent
    db.executescript((root / 'schema.sql').read_text())
    db.executescript((root / 'planning.sql').read_text())

@contextmanager
def atomic(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise

def post(db, *, occurred_on, kind, description, entries, category='', salary_period=None, rate=None, rate_date=None, rate_source=None):
    date.fromisoformat(occurred_on)
    if kind not in ('income', 'expense', 'exchange', 'adjustment'):
        raise ValueError('Jenis transaksi tidak valid.')
    if not isinstance(description, str) or not description.strip() or len(description) > 200:
        raise ValueError('Deskripsi wajib diisi, maksimal 200 karakter.')
    if not isinstance(category, str) or len(category) > 60:
        raise ValueError('Kategori tidak valid.')
    entries = list(entries)
    if not entries:
        raise ValueError('Rincian saldo wajib diisi.')
    for currency, delta in entries:
        if currency not in ('KRW', 'IDR') or type(delta) is not int or not 0 < abs(delta) <= 100_000_000_000_000:
            raise ValueError('Rincian saldo tidak valid.')
    if kind in ('income', 'expense') and len(entries) != 1:
        raise ValueError('Pemasukan/pengeluaran harus satu mata uang.')
    if kind == 'income' and entries[0][1] <= 0:
        raise ValueError('Pemasukan harus positif.')
    if kind == 'expense' and entries[0][1] >= 0:
        raise ValueError('Pengeluaran harus negatif.')
    if kind == 'exchange' and (len(entries) != 2 or len({x[0] for x in entries}) != 2 or entries[0][1] * entries[1][1] >= 0):
        raise ValueError('Penukaran perlu dua mata uang dengan arah berlawanan.')
    if salary_period is not None and (kind != 'income' or entries[0][0] != 'KRW' or salary_period != occurred_on[:7]):
        raise ValueError('Periode gaji tidak sesuai.')
    snapshot = None
    if rate is not None:
        snapshot = str(exchange_rate(rate))
        date.fromisoformat(rate_date)
        if not isinstance(rate_source, str) or not rate_source.strip() or len(rate_source) > 100:
            raise ValueError('Sumber kurs wajib diisi.')
    elif rate_date is not None or rate_source is not None:
        raise ValueError('Metadata kurs harus lengkap.')
    if any(currency == 'KRW' for currency, _ in entries) and snapshot is None:
        raise ValueError('Transaksi KRW membutuhkan kurs acuan tersimpan.')
    db.execute('SAVEPOINT v2_post')
    try:
        cursor = db.execute('INSERT INTO v2_transactions(occurred_on,kind,description,category,salary_period) VALUES(?,?,?,?,?)',
            (occurred_on, kind, description.strip(), category, salary_period))
        tid = cursor.lastrowid
        db.executemany('INSERT INTO v2_entries(transaction_id,currency,delta,idr_per_krw,rate_date,rate_source) VALUES(?,?,?,?,?,?)',
            [(tid, currency, delta, snapshot, rate_date, rate_source) for currency, delta in entries])
        db.execute('RELEASE v2_post')
        return tid
    except Exception:
        db.execute('ROLLBACK TO v2_post')
        db.execute('RELEASE v2_post')
        raise

def balances(db):
    result = {'KRW': 0, 'IDR': 0}
    result.update(db.execute('SELECT e.currency,SUM(e.delta) FROM v2_entries e JOIN v2_transactions t ON t.id=e.transaction_id WHERE t.voided_at IS NULL GROUP BY e.currency'))
    return result
