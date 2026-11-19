"""Optional read-only preview entrypoint. Not used by current deployment."""
import os
from pathlib import Path

legacy_path=Path(os.environ.get('DB_PATH','data/arus.sqlite3')).resolve()
preview=os.environ.get('V2_DB_PATH')
if not preview:
    raise RuntimeError('Set V2_DB_PATH ke database pratinjau terpisah.')
preview_path=Path(preview).resolve()
if preview_path == legacy_path:
    raise RuntimeError('Database pratinjau harus berbeda dari database lama.')
if not legacy_path.is_file():
    raise RuntimeError('DB_PATH harus menunjuk database akun lama yang sudah ada untuk login.')

from app import app, authorized
from v2.ledger import connect, initialize
from v2.dashboard import register_dashboard

preview_path.parent.mkdir(parents=True,exist_ok=True)
with connect(str(preview_path)) as db:
    initialize(db)
register_dashboard(app,authorized,str(preview_path))
