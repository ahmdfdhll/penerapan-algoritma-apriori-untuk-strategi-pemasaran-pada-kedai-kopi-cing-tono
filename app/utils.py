from datetime import datetime
import re


def format_rupiah(angka: int) -> str:
    """Format angka menjadi format Rupiah Indonesia. Contoh: 15000 → Rp 15.000"""
    return f"Rp {angka:,.0f}".replace(",", ".")


def generate_kode_transaksi(tanggal: datetime, urutan: int) -> str:
    """Generate kode transaksi unik. Contoh: TRX-20240101-0001"""
    tgl_str = tanggal.strftime('%Y%m%d')
    return f"TRX-{tgl_str}-{urutan:04d}"


def tanggal_indo(dt: datetime) -> str:
    """Format datetime ke format tanggal Indonesia. Contoh: Senin, 01 Januari 2024"""
    HARI = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
    BULAN = [
        '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
        'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
    ]
    hari  = HARI[dt.weekday()]
    bulan = BULAN[dt.month]
    return f"{hari}, {dt.day:02d} {bulan} {dt.year}"


def hitung_urutan_hari_ini(model_transaksi, tanggal: datetime) -> int:
    """Hitung berapa transaksi sudah terjadi hari ini untuk auto-increment kode."""
    from sqlalchemy import func
    mulai = tanggal.replace(hour=0, minute=0, second=0, microsecond=0)
    akhir = tanggal.replace(hour=23, minute=59, second=59, microsecond=999999)
    count = model_transaksi.query.filter(
        model_transaksi.tanggal.between(mulai, akhir)
    ).count()
    return count + 1


# Kata kunci minuman DINGIN. Dicek lebih dulu supaya item seperti "Fanta Susu"
# atau "Zoda Susu" (soda dingin dicampur susu) tetap dikenali dingin, bukan
# ikut ke kata "susu" yang defaultnya panas.
# Catatan: kata umum seperti "dingin"/"segar"/"seger" sengaja TIDAK dipakai
# karena sering muncul di deskripsi makanan tanpa berkaitan dengan menu itu
# sendiri (mis. "...cocok buat cuaca dingin", bukan berarti menunya dingin).
_KATA_MINUMAN_DINGIN = [
    'es', 'ice', 'iced', 'jus', 'juice', 'float', 'squash', 'soda',
    'milkshake', 'smoothie', 'jeruk', 'nutrisari', 'fanta', 'zoda',
    'klepon', 'freeze', 'kukubima', 'extrajoss', 'beng-beng', 'pop ice',
]

# Kata kunci minuman PANAS (termasuk nama merk/produk yang lazim disajikan
# panas di warkop, walau bisa juga direquest dingin oleh pembeli).
# Catatan: kata umum "hangat"/"panas" sengaja TIDAK dipakai karena sering
# muncul di deskripsi makanan (mis. "nasi hangat", "disajikan hangat").
_KATA_MINUMAN_PANAS = [
    'kopi', 'coffee', 'teh', 'wedang', 'jahe', 'cokelat', 'coklat', 'susu',
    'americano', 'cappuccino', 'latte', 'espresso', 'mocha', 'macchiato',
    'kapal api', 'indocafe', 'nescafe', 'milo', 'ovaltine', 'dancow',
    'chocolatos', 'good day',
]


def _mengandung_kata(teks: str, daftar_kata) -> bool:
    """Cek apakah salah satu kata pada daftar_kata muncul di teks sebagai
    kata utuh (pakai batas kata \\b), supaya tidak salah tangkap kata yang
    kebetulan jadi bagian dari kata lain (mis. 'es' di dalam 'pedes')."""
    for kata in daftar_kata:
        pola = r'\b' + re.escape(kata) + r'\b'
        if re.search(pola, teks):
            return True
    return False


def pilih_emoji_menu(nama: str, kategori: str = '', deskripsi: str = '') -> str:
    """
    Pilih emoji berdasarkan jenis menu:
      - Minuman dingin  -> 🥤 (gelas dingin)
      - Minuman panas   -> ☕ (cangkir)
      - Makanan (selain itu) -> 🍽️ (piring)

    Mempertimbangkan nama menu, kategori, dan deskripsi (kalau ada) supaya
    lebih akurat untuk minuman bermerk seperti "Kapal Api", "Indocafe",
    "Milo", dll.
    """
    teks = f"{nama} {kategori} {deskripsi}".lower()

    if _mengandung_kata(teks, _KATA_MINUMAN_DINGIN):
        return '🥤'

    if _mengandung_kata(teks, _KATA_MINUMAN_PANAS):
        return '☕'

    # Fallback: kalau kategorinya "Minuman" tapi tidak ada kata kunci yang
    # cocok, tetap tampilkan ikon minuman (cangkir) daripada piring.
    if 'minuman' in kategori.lower():
        return '☕'

    return '🍽️'