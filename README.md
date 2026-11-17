# Arus Mobile

MVP keuangan pribadi satu akun dengan UI bergaya m-banking. Flask, SQLite, Gunicorn, Docker Compose dan Caddy. Bukan bank dan tidak melakukan transfer uang.

## Fitur dan batasan

Login password, CSRF, cookie HttpOnly/SameSite/Secure, sesi 8 jam, throttle login. Saldo awal, pemasukan/pengeluaran dan filter bulan. Target dana darurat nominal langsung atau pengeluaran acuan dikali bulan. Impian, prioritas, rencana setoran tetap/persentase, jeda dan alokasi tabungan. Angsuran dengan pembayaran manual. Piutang lama/baru serta pengembalian pokok terpisah dari penghasilan. Ekspor JSON.

Data awal kosong. Satu saldo gabungan kas/rekening, IDR bulat, maksimal Rp100 miliar per input. Rencana setoran tidak otomatis menambah tabungan; alokasi tidak mengurangi total kas. Tidak ada multiuser, MFA, rekening terpisah, notifikasi otomatis, transaksi berulang, edit/hapus transaksi, impor JSON, atau bunga otomatis. Penyimpanan MVP berupa satu dokumen JSON di SQLite dengan penulisan atomik, untuk penggunaan pribadi kecil. Belum diaudit keamanan independen.

## Instalasi VPS

Docker Engine dan Compose plugin harus sudah terpasang. Domain harus diarahkan ke VPS, port 80/443 tersedia. Bila reverse proxy lain memakai port tersebut, integrasikan terlebih dahulu. Repo private memerlukan akses GitHub, misalnya SSH deploy key read-only.

```sh
git clone git@github.com:macdevi/arus-mobile.git
cd arus-mobile
cp .env.example .env
chmod 600 .env
openssl rand -hex 48
```

Edit .env. DOMAIN adalah hostname tanpa https://. SECRET_KEY diisi hasil acak, bukan nilai contoh. Jangan commit .env. Kemudian:

```sh
docker compose config --quiet
docker compose build
docker compose run --rm app python manage.py init-admin
docker compose up -d
docker compose ps
docker compose logs --tail=100 app caddy
```

Buka https://DOMAIN-ANDA. Login dengan password yang dibuat interaktif (14-256 karakter), tidak ada password default. Di Pengaturan isi saldo awal sebelum semua transaksi, penghasilan rencana dan anggaran termasuk angsuran. Target dana darurat memiliki acuan pengeluaran tersendiri.

Cookie Secure mengharuskan HTTPS. Jangan expose port 8000 ke internet. SECRET_KEY tetap sama antar restart. Hash password berada di database, bukan source. Tanggal otomatis mengikuti browser. Jatuh tempo angsuran berikutnya harus diisi manual bila belum lunas.

## Backup dan password

```sh
mkdir -p backups
chmod 700 backups
docker compose exec app python manage.py backup /data/backup-01.sqlite3
docker compose cp app:/data/backup-01.sqlite3 ./backups/backup-01.sqlite3
chmod 600 backups/backup-01.sqlite3
docker compose exec app rm /data/backup-01.sqlite3
# Ganti password dan batalkan sesi lama:
docker compose exec app python manage.py init-admin
```

Gunakan nama backup baru setiap kali. Backup memuat data pribadi dan hash login. Simpan terenkripsi di lokasi terpisah, bukan GitHub. Ekspor JSON bukan backup akun. Jangan jalankan docker compose down -v karena menghapus data dan sertifikat.

## Restore

Backup data aktif dahulu, lalu hentikan seluruh proses app yang memakai volume. Perintah berikut MENIMPA database aktif:

```sh
docker compose stop app
docker compose run --rm --no-deps --user 0 -v "$PWD/backups:/restore:ro" app python -c "import sqlite3,os; a=sqlite3.connect('file:/restore/backup-01.sqlite3?mode=ro',uri=True); b=sqlite3.connect('/data/arus.sqlite3'); a.backup(b); b.close(); a.close(); os.chown('/data/arus.sqlite3',10001,10001)"
docker compose up -d app
```

Uji restore di lingkungan terpisah. Reset password setelah restore jika perlu membatalkan sesi lama.

## Pengujian dan update

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
# Sesudah backup, update deployment:
git pull --ff-only
docker compose up -d --build
```

CI menjalankan test dan build Docker. Tidak ada migrasi skema lintas versi otomatis. Untuk development localhost saja, set SECRET_KEY acak 48+ karakter dan COOKIE_SECURE=false, buat akun via manage.py, lalu flask --app app run --host 127.0.0.1. Jangan membuka development server ke internet.

Pemeriksaan sintaks Python dan JavaScript lolos saat penyusunan. Runtime test belum dijalankan di lingkungan penyusunan karena Flask tidak tersedia. Status CI harus diperiksa setelah push. Build Docker, TLS, browser end-to-end dan deployment VPS belum diverifikasi. Source ini ditujukan untuk diuji pada staging dahulu, bukan klaim siap produksi tanpa pengujian.
