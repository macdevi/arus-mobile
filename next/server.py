import os, json, secrets, hashlib, time, argparse, getpass, sqlite3
from datetime import timedelta
from functools import wraps
from flask import Flask, request, session, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash
import domain as D

def create_app(config=None):
    app=Flask(__name__); app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY',''),DATABASE=os.environ.get('ARUS_NEXT_DB','data/arus-next.sqlite3'),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','true')=='true',PERMANENT_SESSION_LIFETIME=timedelta(hours=8),MAX_CONTENT_LENGTH=65536)
    if config: app.config.update(config)
    key=app.config['SECRET_KEY']
    if not isinstance(key,str) or len(key)<48 or key.startswith('REPLACE'): raise RuntimeError('SECRET_KEY wajib acak, minimal 48 karakter.')
    app.config['SESSION_COOKIE_NAME']='__Host-arus_next' if app.config['SESSION_COOKIE_SECURE'] else 'arus_next_dev'; D.initialize(app.config['DATABASE'])
    def authorized(fn):
        @wraps(fn)
        def run(*args,**kwargs):
            with D.db(app.config['DATABASE']) as c: version=D.get(c,'auth_version')
            if not session.get('auth') or not version or session.get('version')!=version: return jsonify(error='Silakan login.'),401
            return fn(*args,**kwargs)
        return run
    def payload():
        d=request.get_json(silent=True)
        if not isinstance(d,dict): raise ValueError('Format harus objek JSON.')
        return d
    @app.before_request
    def csrf():
        if request.path.startswith('/api/') and request.method=='POST':
            if not session.get('csrf') or not secrets.compare_digest(session['csrf'],request.headers.get('X-CSRF-Token','')): return jsonify(error='Token formulir tidak valid.'),403
    @app.after_request
    def headers(r):
        r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'}); r.headers.setdefault('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'"); return r
    @app.errorhandler(ValueError)
    def invalid(e): return jsonify(error=str(e)),400
    @app.errorhandler(413)
    def oversized(e): return jsonify(error='Permintaan terlalu besar.'),413
    @app.get('/health')
    def health():
        with D.db(app.config['DATABASE']) as c: c.execute('SELECT 1 FROM tx LIMIT 1')
        return jsonify(status='ok')
    @app.get('/')
    def index():
        nonce=secrets.token_urlsafe(24); r=app.make_response(render_template('index.html',nonce=nonce)); r.headers['Content-Security-Policy']=f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"; return r
    @app.get('/api/session')
    def session_info():
        session.setdefault('csrf',secrets.token_urlsafe(32))
        with D.db(app.config['DATABASE']) as c: version=D.get(c,'auth_version')
        return jsonify(csrf=session['csrf'],authenticated=bool(session.get('auth') and version and session.get('version')==version))
    @app.post('/api/login')
    def login():
        p=payload().get('password'); now=time.time()
        if not isinstance(p,str) or len(p)>256: return jsonify(error='Login gagal.'),401
        with D.db(app.config['DATABASE'],True) as c:
            throttle=D.get(c,'throttle',dict(count=0,until=0))
            if throttle['count']>=5 and throttle['until']>now: return jsonify(error='Tunggu 15 menit.'),429
            hashed=D.get(c,'password_hash')
            if not hashed or not check_password_hash(hashed,p):
                D.put(c,'throttle',dict(count=throttle['count']+1 if throttle['until']>now else 1,until=now+900)); return jsonify(error='Login gagal.'),401
            version=D.get(c,'auth_version'); D.put(c,'throttle',dict(count=0,until=0))
        session.clear(); session.update(auth=True,version=version,csrf=secrets.token_urlsafe(32)); session.permanent=True; return jsonify(csrf=session['csrf'])
    @app.post('/api/logout')
    @authorized
    def logout(): session.clear(); return jsonify(ok=True)
    @app.get('/api/data')
    @authorized
    def data():
        with D.db(app.config['DATABASE']) as c: result=D.snapshot(c,request.args.get('month',D.today().strftime('%Y-%m')))
        return jsonify(result)
    @app.post('/api/action')
    @authorized
    def mutate():
        d=payload(); key=D.text(d.get('request_id'),80); fingerprint=hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with D.db(app.config['DATABASE'],True) as c:
            old=c.execute('SELECT * FROM requests WHERE id=?',(key,)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint: raise ValueError('ID permintaan sudah dipakai untuk data berbeda.')
                return jsonify(json.loads(old['result']))
            if d.get('op')=='password':
                current=d.get('current_password'); new=d.get('new_password')
                if not isinstance(current,str) or len(current)>256 or not check_password_hash(D.get(c,'password_hash',''),current): raise ValueError('Password saat ini tidak sesuai.')
                if not isinstance(new,str) or not 14<=len(new)<=256: raise ValueError('Password baru harus 14 sampai 256 karakter.')
                D.put(c,'password_hash',generate_password_hash(new)); D.put(c,'auth_version',secrets.token_urlsafe(32)); result={'ok':True}
            else: result=D.action(c,d)
            c.execute('INSERT INTO requests VALUES(?,?,?)',(key,fingerprint,json.dumps(result)))
        return jsonify(result)
    @app.get('/api/export')
    @authorized
    def export():
        with D.db(app.config['DATABASE']) as c:
            result={name:[dict(r) for r in c.execute('SELECT * FROM '+name)] for name in ('tx','goals','allocations','loans','payments','rates')}; result['settings']={k:D.get(c,k) for k in ('salary_rules','pauses','opening_set')}
        response=jsonify(result); response.headers['Content-Disposition']='attachment; filename=arus-next-export.json'; return response
    @app.post('/api/rate/refresh')
    @authorized
    def rate_refresh():
        try: D.refresh(app.config['DATABASE'],payload().get('day'))
        except (OSError,ValueError,KeyError,TypeError): return jsonify(error='Kurs internet belum tersedia. Kurs tersimpan dipertahankan.'),502
        return jsonify(ok=True)
    @app.post('/api/salary/run')
    @authorized
    def salary_run(): return jsonify(D.tick(app.config['DATABASE'],budget=1))
    return app

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['init-admin','tick','worker','backup']); parser.add_argument('destination',nargs='?'); args=parser.parse_args(); path=os.environ.get('ARUS_NEXT_DB','data/arus-next.sqlite3'); D.initialize(path)
    if args.command=='init-admin':
        p=getpass.getpass('Password baru (14-256 karakter): ')
        if not 14<=len(p)<=256 or p!=getpass.getpass('Ulangi password: '): raise SystemExit('Password tidak valid atau konfirmasi berbeda.')
        with D.db(path,True) as c: D.put(c,'password_hash',generate_password_hash(p)); D.put(c,'auth_version',secrets.token_urlsafe(32)); D.put(c,'throttle',dict(count=0,until=0))
    elif args.command=='backup':
        if not args.destination: raise SystemExit('Isi tujuan backup baru.')
        fd=os.open(args.destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd); src=sqlite3.connect(path); dst=sqlite3.connect(args.destination)
        try: src.backup(dst)
        finally: src.close(); dst.close()
    elif args.command=='tick': print(json.dumps(D.tick(path)))
    else:
        while True:
            try: print(json.dumps(D.tick(path)),flush=True)
            except Exception as e: print(json.dumps({'error':type(e).__name__}),flush=True)
            time.sleep(300)
if __name__=='__main__': main()
