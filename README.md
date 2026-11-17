# Arus Mobile

Aplikasi keuangan pribadi satu akun dengan desain mobile-first bergaya m-banking. Bukan layanan perbankan dan tidak melakukan transfer uang.

## Status repository

Commit ini hanya fondasi deployment. Backend app.py, manage.py, templates, static, serta pengujian belum diunggah. Jangan deploy commit ini sebelum source aplikasi lengkap tersedia.

Paket lengkap disiapkan untuk login akun pribadi, penyimpanan SQLite, transaksi, target dana darurat/impian, alokasi tabungan, angsuran, serta piutang. Data awal kosong, bukan contoh saldo. Fitur versi pertama tidak mencakup multiuser, rekening terpisah, notifikasi otomatis, MFA, edit/hapus transaksi, atau koneksi bank.

## Prasyarat setelah source lengkap tersedia

VPS Linux dengan Docker Engine dan Compose plugin. Domain/subdomain diarahkan ke VPS. Port 80 dan 443 tersedia untuk Caddy. Jika port tersebut sudah digunakan reverse proxy lain, integrasikan proxy yang ada terlebih dahulu. Repository private membutuhkan SSH deploy key read-only atau akses GitHub yang sesuai. Jangan membuka port 8000 ke internet.

## Instalasi setelah source lengkap tersedia

```sh
git clone git@github.com:macdevi/arus-mobile.git
cd arus-mobile
cp .env.example .env
chmod 600 .env
openssl rand -hex 48
```

Edit .env. DOMAIN berupa hostname tanpa https://. SECRET_KEY diisi hasil acak dari perintah di atas. Jangan commit .env atau menyimpan password asli dalam source.

```sh
docker compose config --quiet
docker compose build
docker compose run --rm app python manage.py init-admin
docker compose up -d
docker compose ps
docker compose logs --tail=100 app caddy
```

init-admin meminta password secara interaktif, minimal 14 karakter. Tidak ada password default atau registrasi publik. Akses melalui HTTPS, bukan HTTP. COOKIE_SECURE aktif. Login, buka Pengaturan dan isi saldo awal sebelum transaksi pertama. Gunakan target dan alokasi secara terpisah: rencana setoran tidak otomatis menambah tabungan. Pokok piutang bukan pendapatan.

## Backup setelah source lengkap tersedia

Backup berisi data pribadi dan hash login. Simpan terenkripsi di lokasi terpisah, bukan GitHub. Nama backup harus baru setiap kali.

```sh
mkdir -p backups
chmod 700 backups
docker compose exec app python manage.py backup /data/backup-01.sqlite3
docker compose cp app:/data/backup-01.sqlite3 ./backups/backup-01.sqlite3
chmod 600 backups/backup-01.sqlite3
docker compose exec app rm /data/backup-01.sqlite3
```

Jangan menjalankan docker compose down -v kecuali ingin menghapus data dan sertifikat. Buat backup sebelum setiap update. Uji pemulihan pada lingkungan terpisah. Ekspor JSON dari aplikasi bukan backup lengkap akun.

## Verifikasi

Pemeriksaan sintaks source Python dan JavaScript pada paket yang disiapkan telah lolos. Runtime test belum dijalankan di lingkungan penyusunan karena Flask tidak tersedia. Build Docker, HTTPS, pengujian browser, serta deployment VPS belum diverifikasi. Ini MVP pribadi, bukan aplikasi dengan audit keamanan tingkat bank.
