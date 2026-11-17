# Deployment VPS bersama billing: HTTPS 8443

Target: https://bill.macdevi.cloud:8443. Nginx host tetap melayani billing di 80/443. Arus memakai container tersendiri pada 127.0.0.1:18080 dan database volume tersendiri. Jangan menjalankan Compose default untuk deployment ini karena service Caddy-nya memublikasikan port 80/443. Selalu gunakan -p arus-mobile -f compose.vps.yaml. Jangan gabungkan file ini dengan compose.yaml.

## Kondisi yang sudah dilaporkan operator

Ubuntu 24.04.4, Nginx aktif, Docker 29.1.3 dan Compose 2.40.3. Build dan enam test awal lolos pada VPS. Port 8443/18080 tidak memiliki listener saat diperiksa. Sertifikat bill.macdevi.cloud sudah tercantum dalam konfigurasi Nginx pada path yang digunakan file deploy. Kondisi port dan sertifikat harus diperiksa lagi bila berubah. Konfigurasi 8443 ini belum diuji pada VPS saat ditulis.

## 1. Ambil pembaruan dan buat secret permanen

```sh
cd /opt/arus-mobile
git pull --ff-only
```

Jalankan blok ini untuk membuat .env hanya bila belum ada, tanpa menampilkan secret:

```sh
(
  set -e
  cd /opt/arus-mobile
  if [ ! -e .env ]; then
    umask 077
    key="$(openssl rand -hex 48)"
    printf 'SECRET_KEY=%s\n' "$key" > .env
    unset key
  fi
  chmod 600 .env
  docker compose -p arus-mobile -f compose.vps.yaml config --quiet
)
```

.env yang sudah ada tidak ditimpa. Bila masih berisi placeholder, ganti SECRET_KEY dengan nilai acak permanen. Jangan kirim .env ke chat atau GitHub. DOMAIN tidak diperlukan pada Compose khusus ini.

## 2. Build, test, buat akun dan jalankan app

Jalankan dari /opt/arus-mobile. Berhenti jika ada kegagalan:

```sh
docker compose -p arus-mobile -f compose.vps.yaml build app && \
docker compose -p arus-mobile -f compose.vps.yaml run --rm --no-deps app python -m unittest discover -s tests -v
```

Setelah test OK, buat password pertama. Jalankan init-admin hanya jika memang hendak membuat/mengganti password karena ini membatalkan sesi lama:

```sh
docker compose -p arus-mobile -f compose.vps.yaml run --rm --no-deps app python manage.py init-admin
docker compose -p arus-mobile -f compose.vps.yaml up -d app
docker compose -p arus-mobile -f compose.vps.yaml ps
curl --fail --show-error http://127.0.0.1:18080/health
```

Jika belum merespons, periksa log; jangan lanjut Nginx sebelum health mengembalikan status ok:

```sh
docker compose -p arus-mobile -f compose.vps.yaml logs --tail=80 app
```

## 3. Tambahkan site Nginx terpisah

Tidak mengedit file site billing. Pastikan /etc/nginx/nginx.conf memuat /etc/nginx/conf.d/*.conf. Periksa sebelum menyalin:

```sh
nginx -t
grep -n 'include.*conf.d' /etc/nginx/nginx.conf
test -r /etc/letsencrypt/live/bill.macdevi.cloud/fullchain.pem
test -r /etc/letsencrypt/live/bill.macdevi.cloud/privkey.pem
```

Jika baseline gagal atau include tidak tersedia, berhenti. Setelah semua sesuai, jalankan blok berikut; file tujuan yang sudah ada tidak ditimpa:

```sh
(
  set -e
  cd /opt/arus-mobile
  dest=/etc/nginx/conf.d/arus-8443.conf
  if [ -e "$dest" ]; then
    echo 'Konfigurasi Arus sudah ada. Tinjau sebelum mengganti.'
    exit 1
  fi
  nginx -t
  install -m 644 deploy/nginx-arus-8443.conf "$dest"
  if ! nginx -t; then
    rm -f "$dest"
    echo 'Konfigurasi baru dibatalkan; Nginx belum di-reload.'
    exit 1
  fi
  if ! systemctl reload nginx; then
    rm -f "$dest"
    echo 'Reload gagal. File baru dihapus; periksa status/log Nginx.'
    exit 1
  fi
)
```

Reload merupakan perubahan pada layanan Nginx bersama, bukan jaminan nol gangguan. Jangan restart PHP-FPM, worker billing, atau menjalankan DEPLOY.sh billing untuk instalasi Arus. Jangan cetak isi private key.

## 4. Verifikasi HTTPS lokal lalu akses luar

```sh
curl --fail --show-error --resolve bill.macdevi.cloud:8443:127.0.0.1 https://bill.macdevi.cloud:8443/health
ss -ltnp '( sport = :8443 or sport = :18080 )'
ufw status verbose
```

Jangan memakai curl -k untuk menyembunyikan error sertifikat. Jika UFW aktif dan kebijakan operator mengizinkan akses publik, tambahkan hanya aturan TCP port Arus:

```sh
ufw allow 8443/tcp comment 'Arus HTTPS'
```

Jangan enable/disable/reset firewall secara sembarang. Jika UFW tidak aktif, tidak perlu mengaktifkannya demi Arus. Security group/firewall provider atau proxy DNS mungkin memerlukan aturan terpisah. Jangan membuka port 18080 ke internet. Periksa billing pada URL aslinya setelah reload. Buka https://bill.macdevi.cloud:8443 untuk Arus.

## Cookie dan isolasi

Gunicorn pada Compose ini menggunakan wsgi:app, dengan cookie __Host-arus_session, Secure, Path=/ dan tanpa Domain. Nama unik mengurangi benturan cookie, tetapi cookie hostname yang sama tidak terisolasi berdasarkan port. Dua aplikasi pada hostname sama tetap harus sama-sama dipercaya; ini bukan isolasi setara subdomain terpisah.

## Operasional dan rollback

Selalu pakai -p arus-mobile -f compose.vps.yaml untuk up, exec, logs dan backup. Proyek/volume sama dengan pengujian sebelumnya: arus-mobile dan arus_data. Secret pengujian sebelumnya bukan password akun dan bukan secret permanen. Untuk backup ikuti README tetapi tambahkan dua opsi tersebut pada setiap perintah Compose. Jangan down -v.

Untuk menonaktifkan endpoint Arus, hapus hanya /etc/nginx/conf.d/arus-8443.conf yang dibuat panduan ini, jalankan nginx -t lalu reload bila valid. Hentikan app dengan docker compose -p arus-mobile -f compose.vps.yaml stop app. Data volume tetap ada. Bila aturan UFW tadi benar-benar dibuat khusus Arus, operator dapat menghapus aturan tersebut. Jangan menghapus sertifikat bill.macdevi.cloud karena dipakai billing.
