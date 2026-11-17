import sys, getpass, secrets, sqlite3, os
from werkzeug.security import generate_password_hash
from app import db, DB_PATH

if len(sys.argv)<2:
    raise SystemExit('Usage: python manage.py init-admin | backup /data/backup.sqlite3')
if sys.argv[1]=='init-admin':
    p=getpass.getpass('Password baru (14-256 karakter): ')
    if not 14<=len(p)<=256 or p!=getpass.getpass('Ulangi password: '):
        raise SystemExit('Password tidak cocok atau panjang tidak valid.')
    with db(True) as c:
        c.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('password_hash',generate_password_hash(p)))
        c.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('auth_version',secrets.token_urlsafe(32)))
        c.execute('DELETE FROM throttle')
    print('Hash password diperbarui. Sesi lama dibatalkan.')
elif sys.argv[1]=='backup' and len(sys.argv)==3:
    path=sys.argv[2]
    if os.path.exists(path) or os.path.abspath(path)==os.path.abspath(DB_PATH):
        raise SystemExit('Tujuan harus file baru.')
    src=sqlite3.connect(DB_PATH)
    dst=sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    os.chmod(path,0o600)
    print('Backup dibuat:',path)
else:
    raise SystemExit('Perintah tidak valid.')
