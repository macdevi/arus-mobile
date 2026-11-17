import os, json, sqlite3, secrets, time
from pathlib import Path
from datetime import date, timedelta
from contextlib import contextmanager
from functools import wraps
from flask import Flask, request, session, jsonify, render_template
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

SECRET = os.environ.get('SECRET_KEY', '')
if len(SECRET) < 48 or SECRET.startswith('REPLACE_'):
    raise RuntimeError('SECRET_KEY wajib acak, minimal 48 karakter.')
DB_PATH = os.environ.get('DB_PATH', 'data/arus.sqlite3')
app = Flask(__name__)
app.secret_key = SECRET
app.config.update(MAX_CONTENT_LENGTH=65536, SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', 'true') == 'true',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)

@contextmanager
def db(write=False):
    c = sqlite3.connect(DB_PATH, timeout=15)
    try:
        if write:
            c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def initial():
    return dict(settings=dict(name='Akun Keuangan', opening=0, income=0, budget=0, payday=1),
                transactions=[], goals=[], obligations=[])

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
with db() as c:
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS throttle (id INTEGER PRIMARY KEY, failures INTEGER, until REAL)')
    c.execute('INSERT OR IGNORE INTO state VALUES (1,?)', (json.dumps(initial()),))

def text(v, limit=100):
    if not isinstance(v,str) or not v.strip() or len(v.strip()) > limit:
        raise ValueError('Teks wajib diisi dan tidak boleh terlalu panjang.')
    return v.strip()

def money(v, minimum=0, maximum=100_000_000_000):
    if type(v) is not int or not minimum <= v <= maximum:
        raise ValueError('Nominal harus rupiah bulat dalam batas yang diizinkan.')
    return v

def choose(v, options):
    if v not in options:
        raise ValueError('Pilihan tidak valid.')
    return v

def day(v):
    return date.fromisoformat(text(v,10)).isoformat()

def cash(s):
    balance=s['settings']['opening']+sum(t['amount'] if t['kind'] in ('income','receivable_in') else -t['amount'] for t in s['transactions'])
    allocated=sum(g['saved'] for g in s['goals'])
    return dict(balance=balance, allocated=allocated, free=balance-allocated)

def getstate(c):
    return json.loads(c.execute('SELECT body FROM state WHERE id=1').fetchone()[0])

def authorized(fn):
    @wraps(fn)
    def run(*args,**kwargs):
        with db() as c:
            v=c.execute("SELECT value FROM config WHERE key='auth_version'").fetchone()
        if not session.get('auth') or not v or session.get('version') != v[0]:
            session.clear()
            return jsonify(error='Silakan login kembali.'),401
        return fn(*args,**kwargs)
    return run

@app.before_request
def csrf_check():
    if request.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
        token=session.get('csrf','')
        if not token or not secrets.compare_digest(token,request.headers.get('X-CSRF-Token','')):
            return jsonify(error='Token formulir kedaluwarsa. Muat ulang halaman.'),403

@app.after_request
def headers(r):
    r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'})
    if not r.headers.get('Content-Security-Policy'):
        r.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'"
    return r

@app.errorhandler(ValueError)
def invalid(e):
    return jsonify(error=str(e)),400

@app.errorhandler(413)
def oversized(e):
    return jsonify(error='Permintaan terlalu besar.'),413

def payload():
    d=request.get_json(silent=True)
    if not isinstance(d,dict):
        raise ValueError('Format permintaan harus objek JSON.')
    return d

@app.get('/')
def index():
    nonce=secrets.token_urlsafe(24)
    r=app.make_response(render_template('index.html',nonce=nonce))
    r.headers['Content-Security-Policy']=f"default-src 'self'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return r

@app.get('/health')
def health():
    with db() as c:
        c.execute('SELECT id FROM state').fetchone()
    return jsonify(status='ok')

@app.get('/api/session')
def session_info():
    session.setdefault('csrf',secrets.token_urlsafe(32))
    with db() as c:
        v=c.execute("SELECT value FROM config WHERE key='auth_version'").fetchone()
    return jsonify(csrf=session['csrf'],authenticated=bool(session.get('auth') and v and session.get('version')==v[0]))

@app.post('/api/login')
def login():
    password=payload().get('password','')
    if not isinstance(password,str) or len(password)>256:
        return jsonify(error='Login gagal.'),401
    with db(True) as c:
        now=time.time()
        t=c.execute('SELECT failures,until FROM throttle WHERE id=1').fetchone()
        if t and t[0]>=5 and t[1]>now:
            return jsonify(error='Terlalu banyak percobaan. Tunggu 15 menit.'),429
        p=c.execute("SELECT value FROM config WHERE key='password_hash'").fetchone()
        if not p or not check_password_hash(p[0],password):
            count=t[0]+1 if t and t[1]>now else 1
            c.execute('INSERT OR REPLACE INTO throttle VALUES(1,?,?)',(count,now+900))
            return jsonify(error='Login gagal atau akun belum diinisialisasi.'),401
        v=c.execute("SELECT value FROM config WHERE key='auth_version'").fetchone()[0]
        c.execute('DELETE FROM throttle')
    session.clear()
    session.update(auth=True,version=v,csrf=secrets.token_urlsafe(32))
    session.permanent=True
    return jsonify(csrf=session['csrf'])

@app.post('/api/logout')
@authorized
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get('/api/state')
@authorized
def read():
    with db() as c:
        s=getstate(c)
    return jsonify(**s,totals=cash(s))

@app.post('/api/change')
@authorized
def change():
    d=payload()
    op=d.get('op')
    with db(True) as c:
        s=getstate(c)
        if op=='settings':
            s['settings']=dict(name=text(d.get('name'),60),opening=money(d.get('opening')),
                income=money(d.get('income')),budget=money(d.get('budget')),payday=money(d.get('payday'),1,28))
        elif op=='transaction':
            kind=choose(d.get('kind'),('income','expense'))
            n=money(d.get('amount'),1)
            if kind=='expense' and n>cash(s)['balance']:
                raise ValueError('Saldo kas tidak mencukupi.')
            s['transactions'].append(dict(id=secrets.token_hex(12),name=text(d.get('name')),kind=kind,
                amount=n,category=text(d.get('category'),50),date=day(d.get('date'))))
        elif op=='goal':
            old=next((g for g in s['goals'] if g['id']==d.get('id')),None)
            if d.get('id') and not old:
                raise ValueError('Target tidak ditemukan.')
            kind=choose(d.get('kind'),('dream','emergency'))
            if old and old['kind']!=kind:
                raise ValueError('Jenis target tidak dapat diubah.')
            if kind=='emergency' and any(g['kind']=='emergency' and g is not old for g in s['goals']):
                raise ValueError('Dana darurat sudah ada. Ubah target yang tersedia.')
            mode=choose(d.get('mode'),('fixed','multiple'))
            if kind=='dream' and mode!='fixed':
                raise ValueError('Impian memakai nominal langsung.')
            base=money(d.get('base',0))
            months=money(d.get('months',1),1,120)
            target=money(base*months if mode=='multiple' else d.get('target'),1)
            method=choose(d.get('method'),('fixed','percent'))
            contribution=money(d.get('contribution'),0,100 if method=='percent' else 100_000_000_000)
            if type(d.get('active')) is not bool:
                raise ValueError('Status target tidak valid.')
            saved=old['saved'] if old else money(d.get('saved',0))
            if saved>target or (not old and saved>max(0,cash(s)['free'])):
                raise ValueError('Dana terkumpul melebihi target atau saldo bebas.')
            g=dict(id=old['id'] if old else secrets.token_hex(12),kind=kind,mode=mode,
                name=text(d.get('name'),60),target=target,base=base,months=months,saved=saved,
                deadline=day(d.get('deadline')),method=method,contribution=contribution,
                priority=choose(d.get('priority'),('Tinggi','Sedang','Rendah')),
                account=text(d.get('account'),60),active=d['active'])
            if old:
                s['goals'][s['goals'].index(old)]=g
            else:
                s['goals'].append(g)
        elif op=='allocate':
            g=next((g for g in s['goals'] if g['id']==d.get('id')),None)
            if not g:
                raise ValueError('Target tidak ditemukan.')
            n=money(d.get('amount'),1)
            direction=choose(d.get('direction'),('add','release'))
            if direction=='add':
                if n>max(0,cash(s)['free']) or g['saved']+n>g['target']:
                    raise ValueError('Saldo bebas tidak cukup atau alokasi melebihi target.')
                g['saved']+=n
            else:
                if n>g['saved']:
                    raise ValueError('Alokasi target tidak mencukupi.')
                g['saved']-=n
        elif op=='obligation':
            kind=choose(d.get('kind'),('installment','receivable'))
            total=money(d.get('total'),1)
            monthly=money(d.get('monthly',0))
            source=choose(d.get('source'),('opening','now'))
            if kind=='installment' and not 1<=monthly<=total:
                raise ValueError('Angsuran bulanan tidak valid.')
            o=dict(id=secrets.token_hex(12),name=text(d.get('name'),80),kind=kind,total=total,
                monthly=monthly,paid=0,due=day(d.get('due')))
            if kind=='receivable' and source=='now':
                if total>cash(s)['balance']:
                    raise ValueError('Saldo tidak cukup untuk pinjaman baru.')
                s['transactions'].append(dict(id=secrets.token_hex(12),name='Pinjaman: '+o['name'],
                    kind='receivable_out',amount=total,category='Pokok piutang',date=day(d.get('date'))))
            s['obligations'].append(o)
        elif op=='pay':
            o=next((o for o in s['obligations'] if o['id']==d.get('id')),None)
            n=money(d.get('amount'),1)
            if not o or n>o['total']-o['paid']:
                raise ValueError('Tagihan tidak ditemukan atau pembayaran melebihi sisa.')
            next_due=day(d['next_due']) if d.get('next_due') else None
            if o['kind']=='installment':
                if n>cash(s)['balance']:
                    raise ValueError('Saldo tidak cukup.')
                if o['paid']+n<o['total'] and not next_due:
                    raise ValueError('Isi jatuh tempo berikutnya jika angsuran belum lunas.')
            o['paid']+=n
            if next_due:
                o['due']=next_due
            s['transactions'].append(dict(id=secrets.token_hex(12),name='Pembayaran: '+o['name'],
                kind='expense' if o['kind']=='installment' else 'receivable_in',amount=n,
                category='Angsuran' if o['kind']=='installment' else 'Pokok piutang',date=day(d.get('date'))))
        else:
            raise ValueError('Operasi tidak dikenali.')
        c.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(s),))
    return jsonify(ok=True)
