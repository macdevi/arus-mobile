# Arus Next: rekonstruksi sumber langsung

Kode mandiri disimpan langsung di branch pengembangan, tanpa ZIP.
Tidak mengimpor aplikasi atau database Arus lama.
Gunakan ARUS_NEXT_DB terpisah dan SECRET_KEY acak minimal 48 karakter.

Commit awal ini menyimpan domain, API, CLI akun, backup, dan worker.
Template antarmuka, pengujian yang disesuaikan dengan pemisahan domain/server,
dan konfigurasi deployment belum disertakan pada commit ini.
Route / masih memerlukan templates/index.html; jangan jalankan sebagai pengganti produksi.

Hasil 57 pengujian dari paket sebelumnya tidak otomatis berlaku untuk rekonstruksi ini.
Pengujian domain, API, Docker, dan browser perlu dijalankan ulang.
Belum siap deploy. Tidak ada perubahan pada main, VPS, Nginx, billing, atau data aktif.

Setelah dependensi tersedia, entrypoint web yang dituju adalah server:create_app().
CLI: python server.py init-admin | tick | worker | backup TUJUAN_BARU.
Tidak ada password bawaan. COOKIE_SECURE secara default true.
COOKIE_SECURE=false hanya untuk pengujian loopback, bukan akses publik.
Worker memeriksa gaji setiap 300 detik; tidak ada worker yang dijalankan oleh commit ini.
Tidak ada perintah penghapusan Arus lama dalam kode ini.
