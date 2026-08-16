# ☕ Kedai Kopi Cing Tono 

Aplikasi manajemen kedai kopi berbasis **Flask + MySQL** dengan fitur POS kasir,
manajemen stok & menu, visualisasi penjualan, dan **analisis Apriori** (Association Rules Mining).

---

## 🗂 Struktur Proyek

```
kedai_kopi_cing_tono/
├── run.py                  # Entry point Flask
├── config.py               # Konfigurasi DB & secret key
├── requirements.txt        # Dependensi Python
└── app/
    ├── __init__.py         # App factory, inisialisasi DB
    ├── models.py           # ORM SQLAlchemy (User, Menu, Transaksi, ...)
    ├── routes.py           # Semua URL routes & API endpoints
    ├── apriori_core.py     # Pipeline algoritma Apriori (mlxtend)
    ├── utils.py            # Helper: format rupiah, kode transaksi, dll
    └── templates/
        ├── base.html       # Layout induk + sidebar navigasi
        ├── login.html      # Halaman autentikasi
        ├── beranda.html    # Dashboard ringkasan
        ├── kasir.html      # POS kasir (AJAX keranjang)
        ├── laporan.html    # Riwayat transaksi + pagination
        ├── eksplorasi.html # Grafik Chart.js (4 chart)
        ├── apriori.html    # Form parameter + tampilan rules
        ├── menu.html       # CRUD menu (grid + table view)
        └── stok.html       # CRUD stok bahan + restok
```

---

## ⚙️ Instalasi & Setup

### 1. Buat virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 2. Install dependensi

```bash
pip install -r requirements.txt
```

### 3. Buat database MySQL

```sql
CREATE DATABASE kedai_kopi_cing_tono
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 4. Konfigurasi koneksi

Edit `config.py` atau set environment variables:

```bash
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=password_anda
export MYSQL_DB=kedai_kopi_cing_tono
```

### 5. Jalankan server

```bash
python run.py
```

Akses di: **http://localhost:5000**

---

## 🔑 Akun Default

| Username | Password  | Role  |
|----------|-----------|-------|
| admin    | admin123  | admin |

---

## 🧩 Fitur Utama

| Modul               | Deskripsi                                              |
|---------------------|--------------------------------------------------------|
| **Kasir / POS**     | AJAX cart, multi-item, cetak struk, kembalian otomatis |
| **Laporan**         | Riwayat transaksi + filter tanggal + detail modal      |
| **Eksplorasi**      | 4 grafik Chart.js: harian, bulanan, kategori, top menu |
| **Analisis Apriori**| Parameter slider, frequent itemsets, association rules |
| **Data Menu**       | CRUD + filter kategori + grid/table view               |
| **Stok Bahan**      | CRUD + restok + progress bar + peringatan stok rendah  |

---

## 📦 Dependensi Utama

| Library             | Versi   | Fungsi                        |
|---------------------|---------|-------------------------------|
| Flask               | 3.0.3   | Web framework                 |
| Flask-SQLAlchemy    | 3.1.1   | ORM database                  |
| Flask-Login         | 0.6.3   | Autentikasi sesi              |
| PyMySQL             | 1.1.1   | Koneksi MySQL                 |
| mlxtend             | 0.23.1  | Algoritma Apriori             |
| pandas              | 2.2.2   | Manipulasi data transaksi     |
| Chart.js (CDN)      | 4.4.3   | Visualisasi grafik frontend   |
| Bootstrap (CDN)     | 5.3.3   | UI framework                  |

---

## 🔌 API Endpoints

| Method | URL                                  | Fungsi                        |
|--------|--------------------------------------|-------------------------------|
| POST   | `/api/kasir/bayar`                   | Proses transaksi              |
| GET    | `/api/menu/list`                     | Daftar menu tersedia          |
| GET    | `/laporan/detail/<id>`               | Detail transaksi (JSON)       |
| GET    | `/api/eksplorasi/penjualan-harian`   | Data grafik harian            |
| GET    | `/api/eksplorasi/penjualan-kategori` | Data grafik kategori          |
| GET    | `/api/eksplorasi/top-menu`           | Top 10 menu terlaris          |
| GET    | `/api/eksplorasi/pendapatan-bulanan` | Pendapatan per bulan          |
