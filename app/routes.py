"""
routes.py
~~~~~~~~~
Blueprint utama yang menangani semua rute web dan API endpoint.
"""

import io
import os
import uuid
import tempfile
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, session, Response, send_file
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, extract

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

from app import db
from app.models import User, Menu, KategoriMenu, StokBahan, Transaksi, DetailTransaksi, ResepMenu
from app.apriori_core import jalankan_apriori, jalankan_apriori_dari_file, statistik_item_populer
from app.utils import format_rupiah, generate_kode_transaksi, hitung_urutan_hari_ini, pilih_emoji_menu

main = Blueprint('main', __name__)


# ══════════════════════════════════════════════════════════
# PEMBATASAN AKSES BERDASARKAN ROLE
# ══════════════════════════════════════════════════════════
# admin  : bebas akses seluruh halaman (tidak dibatasi).
# kasir  : hanya boleh akses Kasir/POS dan Stok Bahan.
# owner  : hanya boleh akses Riwayat Transaksi, Eksplorasi Data,
#          dan Analisis Apriori.

ENDPOINT_KASIR = {
    'main.kasir',
    'main.api_bayar',
    'main.api_menu_list',
    'main.stok',
    'main.stok_tambah',
    'main.stok_edit',
    'main.stok_hapus',
    'main.stok_restok',
    'main.resep_tambah',
    'main.resep_hapus',
    'main.laporan',
    'main.laporan_detail',
    'main.cetak_struk',
    'main.laporan_download_pdf',
}

ENDPOINT_OWNER = {
    'main.beranda',
    'main.laporan',
    'main.laporan_detail',
    'main.cetak_struk',
    'main.laporan_download_pdf',
    'main.eksplorasi',
    'main.api_penjualan_harian',
    'main.api_daftar_bulan_harian',
    'main.api_penjualan_kategori',
    'main.api_top_menu',
    'main.api_pendapatan_bulanan',
    'main.apriori',
    'main.download_pdf_apriori',
    'main.download_pdf_apriori_file',
    'main.download_template_apriori',
}

# Endpoint yang selalu boleh diakses siapa pun yang sudah login.
ENDPOINT_BEBAS = {'main.logout'}


def halaman_utama_role():
    """Tujuan redirect default sesuai role setelah login."""
    if current_user.role == 'kasir':
        return url_for('main.kasir')
    if current_user.role == 'owner':
        return url_for('main.laporan')
    return url_for('main.beranda')


@main.before_request
def batasi_akses_role():
    if not current_user.is_authenticated:
        return

    endpoint = request.endpoint

    if endpoint is None or endpoint in ENDPOINT_BEBAS:
        return

    role = current_user.role

    if role == 'admin':
        return

    if role == 'kasir' and endpoint not in ENDPOINT_KASIR:
        flash('Akses ditolak. Kasir hanya dapat mengakses Kasir/POS, Riwayat Transaksi, dan Stok Bahan.', 'danger')
        return redirect(url_for('main.kasir'))

    if role == 'owner' and endpoint not in ENDPOINT_OWNER:
        flash('Akses ditolak. Owner hanya dapat mengakses Beranda, Riwayat Transaksi, Eksplorasi Data, dan Analisis Apriori.', 'danger')
        return redirect(url_for('main.laporan'))


# ══════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════

@main.route('/', methods=['GET', 'POST'])
@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(halaman_utama_role())

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user, remember=True)
            flash(f'Selamat datang, {user.nama_lengkap}!', 'success')
            return redirect(halaman_utama_role())

        flash('Username atau password salah.', 'danger')

    return render_template('login.html')


@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('main.login'))


# ══════════════════════════════════════════════════════════
# BERANDA / DASHBOARD
# ══════════════════════════════════════════════════════════

@main.route('/beranda')
@login_required
def beranda():
    hari_ini = datetime.now().date()
    bulan_ini = datetime.now().month
    tahun_ini = datetime.now().year

    pendapatan_hari_ini = db.session.query(func.sum(Transaksi.total))\
        .filter(func.date(Transaksi.tanggal) == hari_ini).scalar() or 0

    trx_hari_ini = Transaksi.query.filter(
        func.date(Transaksi.tanggal) == hari_ini
    ).count()

    pendapatan_bulan_ini = db.session.query(func.sum(Transaksi.total))\
        .filter(
            extract('month', Transaksi.tanggal) == bulan_ini,
            extract('year', Transaksi.tanggal) == tahun_ini
        ).scalar() or 0

    trx_bulan_ini = Transaksi.query.filter(
        extract('month', Transaksi.tanggal) == bulan_ini,
        extract('year', Transaksi.tanggal) == tahun_ini
    ).count()

    stok_rendah = StokBahan.query.filter(
        StokBahan.jumlah <= StokBahan.minimum_stok
    ).all()

    transaksi_terbaru = Transaksi.query.order_by(
        Transaksi.tanggal.desc()
    ).limit(5).all()

    top_menu = db.session.query(
        Menu.nama,
        func.sum(DetailTransaksi.jumlah).label('total')
    ).join(DetailTransaksi).group_by(Menu.id, Menu.nama)\
     .order_by(func.sum(DetailTransaksi.jumlah).desc()).limit(5).all()

    return render_template(
        'beranda.html',
        pendapatan_hari_ini=pendapatan_hari_ini,
        trx_hari_ini=trx_hari_ini,
        pendapatan_bulan_ini=pendapatan_bulan_ini,
        trx_bulan_ini=trx_bulan_ini,
        stok_rendah=stok_rendah,
        transaksi_terbaru=transaksi_terbaru,
        top_menu=top_menu,
        format_rupiah=format_rupiah
    )


# ══════════════════════════════════════════════════════════
# KASIR / POS
# ══════════════════════════════════════════════════════════

@main.route('/kasir')
@login_required
def kasir():
    kategoris = KategoriMenu.query.all()
    menus = Menu.query.filter_by(tersedia=True).order_by(Menu.kategori_id, Menu.nama).all()

    return render_template(
        'kasir.html',
        kategoris=kategoris,
        menus=menus,
        format_rupiah=format_rupiah,
        pilih_emoji=pilih_emoji_menu
    )


@main.route('/api/kasir/bayar', methods=['POST'])
@login_required
def api_bayar():
    data = request.get_json()
    items = data.get('items', [])
    bayar = int(data.get('bayar', 0))
    catatan = data.get('catatan', '')

    if not items:
        return jsonify({'status': 'error', 'pesan': 'Keranjang kosong.'}), 400

    total = sum(item['harga_satuan'] * item['jumlah'] for item in items)

    if bayar < total:
        return jsonify({
            'status': 'error',
            'pesan': f'Uang bayar kurang. Total: Rp {total:,}'
        }), 400

    kembalian = bayar - total
    now = datetime.now()
    urutan = hitung_urutan_hari_ini(Transaksi, now)
    kode = generate_kode_transaksi(now, urutan)

    trx = Transaksi(
        kode=kode,
        tanggal=now,
        total=total,
        bayar=bayar,
        kembalian=kembalian,
        user_id=current_user.id,
        catatan=catatan
    )

    db.session.add(trx)
    db.session.flush()

    for item in items:
        menu = Menu.query.get(item['menu_id'])

        if not menu:
            continue

        subtotal = item['harga_satuan'] * item['jumlah']

        detail = DetailTransaksi(
            transaksi_id=trx.id,
            menu_id=item['menu_id'],
            jumlah=item['jumlah'],
            harga_satuan=item['harga_satuan'],
            subtotal=subtotal
        )

        db.session.add(detail)

    db.session.flush()

    # ── Kurangi stok bahan otomatis berdasarkan resep tiap menu ──────
    bahan_rendah = []

    for item in items:
        resep_list = ResepMenu.query.filter_by(menu_id=item['menu_id']).all()

        for resep in resep_list:
            bahan = StokBahan.query.get(resep.bahan_id)

            if not bahan:
                continue

            terpakai = resep.jumlah_terpakai * item['jumlah']
            bahan.jumlah = max(0, bahan.jumlah - terpakai)
            bahan.updated_at = now

            if bahan.is_rendah() and bahan.nama_bahan not in bahan_rendah:
                bahan_rendah.append(bahan.nama_bahan)

    db.session.commit()

    return jsonify({
        'status': 'success',
        'trx_id': trx.id,
        'kode': kode,
        'total': total,
        'kembalian': kembalian,
        'bahan_rendah': bahan_rendah,
        'pesan': f'Transaksi {kode} berhasil disimpan.'
    })


@main.route('/kasir/struk/<int:trx_id>')
@login_required
def cetak_struk(trx_id):
    """Halaman cetak bill/struk untuk satu transaksi (dibuka di tab baru lalu window.print())."""
    trx = Transaksi.query.get_or_404(trx_id)

    return render_template(
        'struk.html',
        trx=trx,
        format_rupiah=format_rupiah
    )


@main.route('/api/menu/list')
@login_required
def api_menu_list():
    kategori_id = request.args.get('kategori_id', type=int)
    q = Menu.query.filter_by(tersedia=True)

    if kategori_id:
        q = q.filter_by(kategori_id=kategori_id)

    menus = q.order_by(Menu.nama).all()

    return jsonify([{
        'id': m.id,
        'nama': m.nama,
        'harga': m.harga,
        'kategori': m.kategori.nama if m.kategori else '-'
    } for m in menus])


# ══════════════════════════════════════════════════════════
# LAPORAN TRANSAKSI
# ══════════════════════════════════════════════════════════

@main.route('/laporan')
@login_required
def laporan():
    halaman = request.args.get('halaman', 1, type=int)
    per_hal = 15
    tgl_dari = request.args.get('tgl_dari', '')
    tgl_ke = request.args.get('tgl_ke', '')

    q = Transaksi.query.order_by(Transaksi.tanggal.desc())

    if tgl_dari:
        q = q.filter(Transaksi.tanggal >= datetime.strptime(tgl_dari, '%Y-%m-%d'))

    if tgl_ke:
        tgl_ke_obj = datetime.strptime(tgl_ke, '%Y-%m-%d') + timedelta(days=1)
        q = q.filter(Transaksi.tanggal < tgl_ke_obj)

    pagination = q.paginate(page=halaman, per_page=per_hal, error_out=False)

    total_periode = db.session.query(func.sum(Transaksi.total)).scalar() or 0

    return render_template(
        'laporan.html',
        transaksis=pagination.items,
        pagination=pagination,
        tgl_dari=tgl_dari,
        tgl_ke=tgl_ke,
        total_periode=total_periode,
        format_rupiah=format_rupiah
    )


@main.route('/laporan/download-pdf')
@login_required
def laporan_download_pdf():
    """Cetak laporan riwayat transaksi (daftar) ke PDF, mengikuti filter tanggal yang aktif."""
    tgl_dari = request.args.get('tgl_dari', '')
    tgl_ke = request.args.get('tgl_ke', '')

    q = Transaksi.query.order_by(Transaksi.tanggal.desc())

    if tgl_dari:
        q = q.filter(Transaksi.tanggal >= datetime.strptime(tgl_dari, '%Y-%m-%d'))

    if tgl_ke:
        tgl_ke_obj = datetime.strptime(tgl_ke, '%Y-%m-%d') + timedelta(days=1)
        q = q.filter(Transaksi.tanggal < tgl_ke_obj)

    transaksis = q.all()
    total_periode = sum(t.total for t in transaksis)

    periode = "Semua Periode"
    if tgl_dari or tgl_ke:
        periode = f"{tgl_dari or '-'} s/d {tgl_ke or '-'}"

    buffer = _buat_pdf_buffer_laporan(transaksis, total_periode, periode)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"laporan_transaksi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mimetype="application/pdf"
    )


def _buat_pdf_buffer_laporan(transaksis, total_periode, periode):
    """Bangun isi PDF laporan riwayat transaksi (daftar transaksi + ringkasan)."""
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=115,
        bottomMargin=110
    )

    styles = getSampleStyleSheet()
    style_center_h3 = ParagraphStyle(
        'CenterH3', parent=styles['Heading3'], alignment=TA_CENTER
    )
    style_center_normal = ParagraphStyle(
        'CenterNormal', parent=styles['Normal'], alignment=TA_CENTER
    )

    nama_penanggung_jawab = current_user.nama_lengkap if current_user.is_authenticated else 'Admin'

    elements = []

    elements.append(Paragraph("<b>Daftar Transaksi</b>", style_center_h3))
    elements.append(Spacer(1, 6))

    data = [["No", "Kode Transaksi", "Tanggal & Waktu", "Kasir", "Total", "Bayar", "Kembalian"]]

    for i, trx in enumerate(transaksis, start=1):
        data.append([
            str(i),
            trx.kode,
            trx.tanggal.strftime('%d/%m/%Y %H:%M'),
            trx.kasir.nama_lengkap,
            format_rupiah(trx.total),
            format_rupiah(trx.bayar),
            format_rupiah(trx.kembalian),
        ])

    if len(transaksis) == 0:
        elements.append(Paragraph("Tidak ada transaksi pada periode ini.", style_center_normal))
    else:
        # Baris penjumlahan (total pendapatan) di baris terakhir tabel.
        baris_total = len(data)
        data.append([
            "", "", "",
            f"TOTAL ({len(transaksis)} transaksi)",
            format_rupiah(total_periode),
            "", ""
        ])

        gaya_total = [
            ("SPAN", (0, baris_total), (3, baris_total)),
            ("FONTNAME", (0, baris_total), (-1, baris_total), "Helvetica-Bold"),
            ("BACKGROUND", (0, baris_total), (-1, baris_total), colors.HexColor("#E8D8C3")),
            ("ALIGN", (3, baris_total), (3, baris_total), "RIGHT"),
            ("ALIGN", (4, baris_total), (4, baris_total), "CENTER"),
        ]

        tabel_transaksi = _buat_tabel_pdf(
            data,
            lebar=[30, 90, 95, 100, 80, 80, 80],
            font_size=8,
            gaya_tambahan=gaya_total
        )
        elements.append(tabel_transaksi)

    def _header_footer(canvas, doc_):
        _gambar_kop_surat_pdf(
            canvas, doc_,
            judul_laporan="Laporan Riwayat Transaksi",
            periode=periode,
            nama_penanggung_jawab=nama_penanggung_jawab
        )

    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer


@main.route('/laporan/detail/<int:trx_id>')
@login_required
def laporan_detail(trx_id):
    trx = Transaksi.query.get_or_404(trx_id)

    return jsonify({
        'kode': trx.kode,
        'tanggal': trx.tanggal.strftime('%d/%m/%Y %H:%M'),
        'kasir': trx.kasir.nama_lengkap,
        'catatan': trx.catatan,
        'total': trx.total,
        'bayar': trx.bayar,
        'kembalian': trx.kembalian,
        'items': [{
            'nama': d.menu.nama,
            'jumlah': d.jumlah,
            'harga_satuan': d.harga_satuan,
            'subtotal': d.subtotal
        } for d in trx.details]
    })


# ══════════════════════════════════════════════════════════
# EKSPLORASI / VISUALISASI
# ══════════════════════════════════════════════════════════

@main.route('/eksplorasi')
@login_required
def eksplorasi():
    return render_template('eksplorasi.html')


@main.route('/api/eksplorasi/penjualan-harian')
@login_required
def api_penjualan_harian():
    """
    Data chart "Penjualan Harian". Menerima parameter opsional ?bulan=YYYY-MM
    untuk melihat data satu bulan kalender penuh (mis. ?bulan=2026-04 untuk
    April 2026). Kalau parameter tidak dikirim / tidak valid, fallback ke
    perilaku lama: 30 hari terakhir dari hari ini.
    """
    bulan_param = request.args.get('bulan', '').strip()

    if bulan_param:
        try:
            tahun_str, bulan_str = bulan_param.split('-')
            tahun, bulan = int(tahun_str), int(bulan_str)
            mulai = datetime(tahun, bulan, 1)
            akhir = datetime(tahun + 1, 1, 1) if bulan == 12 else datetime(tahun, bulan + 1, 1)
        except (ValueError, TypeError):
            akhir = datetime.now()
            mulai = akhir - timedelta(days=29)
    else:
        akhir = datetime.now()
        mulai = akhir - timedelta(days=29)

    hasil = db.session.query(
        func.date(Transaksi.tanggal).label('tgl'),
        func.sum(Transaksi.total).label('total'),
        func.count(Transaksi.id).label('jml')
    ).filter(
        Transaksi.tanggal >= mulai,
        Transaksi.tanggal < akhir
    ).group_by(
        func.date(Transaksi.tanggal)
    ).order_by(
        func.date(Transaksi.tanggal)
    ).all()

    labels = [str(r.tgl) for r in hasil]
    totals = [int(r.total) for r in hasil]
    counts = [int(r.jml) for r in hasil]

    return jsonify({'labels': labels, 'totals': totals, 'counts': counts})


@main.route('/api/eksplorasi/daftar-bulan-harian')
@login_required
def api_daftar_bulan_harian():
    """
    Daftar bulan-bulan yang punya data transaksi, dipakai untuk mengisi
    dropdown filter pada chart "Penjualan Harian". Hanya menampilkan bulan
    yang benar-benar ada transaksinya (tidak menampilkan bulan kosong).
    """
    hasil = db.session.query(
        extract('year', Transaksi.tanggal).label('tahun'),
        extract('month', Transaksi.tanggal).label('bulan')
    ).group_by('tahun', 'bulan').order_by(
        extract('year', Transaksi.tanggal).desc(),
        extract('month', Transaksi.tanggal).desc()
    ).all()

    BULAN = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
             'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    daftar = [{
        'value': f"{int(r.tahun)}-{int(r.bulan):02d}",
        'label': f"{BULAN[int(r.bulan)]} {int(r.tahun)}"
    } for r in hasil]

    return jsonify(daftar)


@main.route('/api/eksplorasi/penjualan-kategori')
@login_required
def api_penjualan_kategori():
    hasil = db.session.query(
        KategoriMenu.nama,
        func.sum(DetailTransaksi.subtotal).label('total')
    ).join(
        Menu, KategoriMenu.id == Menu.kategori_id
    ).join(
        DetailTransaksi, Menu.id == DetailTransaksi.menu_id
    ).group_by(
        KategoriMenu.id,
        KategoriMenu.nama
    ).order_by(
        func.sum(DetailTransaksi.subtotal).desc()
    ).all()

    return jsonify({
        'labels': [r.nama for r in hasil],
        'data': [int(r.total) for r in hasil]
    })


@main.route('/api/eksplorasi/top-menu')
@login_required
def api_top_menu():
    top = statistik_item_populer(10)

    return jsonify({
        'labels': [i['nama'] for i in top],
        'data': [i['total_terjual'] for i in top]
    })


@main.route('/api/eksplorasi/pendapatan-bulanan')
@login_required
def api_pendapatan_bulanan():
    hasil = db.session.query(
        extract('year', Transaksi.tanggal).label('tahun'),
        extract('month', Transaksi.tanggal).label('bulan'),
        func.sum(Transaksi.total).label('total')
    ).group_by(
        'tahun',
        'bulan'
    ).order_by(
        'tahun',
        'bulan'
    ).limit(12).all()

    BULAN = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
             'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']

    labels = [f"{BULAN[int(r.bulan)]} {int(r.tahun)}" for r in hasil]
    data = [int(r.total) for r in hasil]

    return jsonify({'labels': labels, 'data': data})


# ══════════════════════════════════════════════════════════
# ANALISIS APRIORI
# ══════════════════════════════════════════════════════════

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_parameter(value, default):
    try:
        angka = float(value)
    except Exception:
        return default

    if angka > 1:
        angka = angka / 100

    return angka


UPLOAD_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'apriori_cache_cing_tono')


def _simpan_file_cache(file_bytes, filename):
    """
    Simpan file transaksi yang diupload ke folder temp di server, lalu simpan
    path & nama aslinya di session. Tujuannya supaya saat user klik
    "Cetak PDF Laporan", file yang sama bisa dipakai ulang tanpa harus
    upload ulang (karena tombol cetak PDF cuma link GET, bukan form upload).
    """
    os.makedirs(UPLOAD_CACHE_DIR, exist_ok=True)

    file_lama = session.get('apriori_file_path')

    if file_lama and os.path.exists(file_lama):
        try:
            os.remove(file_lama)
        except OSError:
            pass

    ekstensi = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'csv'
    nama_unik = f"{uuid.uuid4().hex}.{ekstensi}"
    path_baru = os.path.join(UPLOAD_CACHE_DIR, nama_unik)

    with open(path_baru, 'wb') as f:
        f.write(file_bytes)

    session['apriori_file_path'] = path_baru
    session['apriori_file_name'] = filename


@main.route('/apriori', methods=['GET', 'POST'])
@login_required
def apriori():
    hasil = None
    min_support = 0.1
    min_confidence = 0.5
    min_lift = 1.0
    tgl_mulai = ''
    tgl_akhir = ''
    sumber_data = 'database'
    nama_file = ''
    preview_cols = []
    preview_rows = []
    file_error = ''

    if request.method == 'POST':
        min_support = parse_parameter(request.form.get('min_support', 0.1), 0.1)
        min_confidence = parse_parameter(request.form.get('min_confidence', 0.5), 0.5)

        try:
            min_lift = float(request.form.get('min_lift', 1.0))
        except Exception:
            min_lift = 1.0

        sumber_data = request.form.get('sumber_data', 'database')

        if sumber_data == 'file':
            uploaded = request.files.get('file_transaksi')

            if not uploaded or uploaded.filename == '':
                file_error = 'Belum ada file yang dipilih.'
            elif not _allowed_file(uploaded.filename):
                file_error = 'Format file tidak didukung. Gunakan CSV atau Excel (.xlsx / .xls).'
            else:
                nama_file = uploaded.filename
                file_bytes = uploaded.read()

                import io as _io
                import pandas as _pd

                try:
                    if nama_file.lower().endswith('.csv'):
                        df_prev = _pd.read_csv(_io.BytesIO(file_bytes))
                    else:
                        df_prev = _pd.read_excel(_io.BytesIO(file_bytes))

                    preview_cols = df_prev.columns.tolist()
                    preview_rows = df_prev.head(5).values.tolist()
                except Exception:
                    pass

                hasil = jalankan_apriori_dari_file(
                    file_bytes=file_bytes,
                    filename=nama_file,
                    min_support=min_support,
                    min_confidence=min_confidence,
                    min_lift=min_lift
                )

                _simpan_file_cache(file_bytes, nama_file)

        else:
            tgl_mulai_str = request.form.get('tgl_mulai', '')
            tgl_akhir_str = request.form.get('tgl_akhir', '')

            tgl_mulai = tgl_mulai_str
            tgl_akhir = tgl_akhir_str

            tgl_mulai_obj = datetime.strptime(tgl_mulai_str, '%Y-%m-%d') if tgl_mulai_str else None

            tgl_akhir_obj = (
                datetime.strptime(tgl_akhir_str, '%Y-%m-%d') + timedelta(days=1)
            ) if tgl_akhir_str else None

            hasil = jalankan_apriori(
                min_support=min_support,
                min_confidence=min_confidence,
                min_lift=min_lift,
                tgl_mulai=tgl_mulai_obj,
                tgl_akhir=tgl_akhir_obj
            )

    total_trx_all = Transaksi.query.count()

    return render_template(
        'apriori.html',
        hasil=hasil,
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift,
        tgl_mulai=tgl_mulai,
        tgl_akhir=tgl_akhir,
        total_trx_all=total_trx_all,
        sumber_data=sumber_data,
        nama_file=nama_file,
        preview_cols=preview_cols,
        preview_rows=preview_rows,
        file_error=file_error
    )


@main.route('/apriori/download-pdf')
@login_required
def download_pdf_apriori():
    min_support = parse_parameter(request.args.get('min_support', 0.1), 0.1)
    min_confidence = parse_parameter(request.args.get('min_confidence', 0.5), 0.5)

    try:
        min_lift = float(request.args.get('min_lift', 1.0))
    except Exception:
        min_lift = 1.0

    tgl_mulai_str = request.args.get('tgl_mulai', '')
    tgl_akhir_str = request.args.get('tgl_akhir', '')

    tgl_mulai_obj = datetime.strptime(tgl_mulai_str, '%Y-%m-%d') if tgl_mulai_str else None
    tgl_akhir_obj = (
        datetime.strptime(tgl_akhir_str, '%Y-%m-%d') + timedelta(days=1)
    ) if tgl_akhir_str else None

    hasil = jalankan_apriori(
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift,
        tgl_mulai=tgl_mulai_obj,
        tgl_akhir=tgl_akhir_obj
    )

    bagian = request.args.get('bagian', 'semua')

    periode = "Database — Semua Periode"

    if tgl_mulai_str or tgl_akhir_str:
        periode = f"Database — {tgl_mulai_str or '-'} s/d {tgl_akhir_str or '-'}"

    buffer = _buat_pdf_buffer_apriori(hasil, min_support, min_confidence, min_lift, periode, bagian)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=_nama_file_pdf(bagian),
        mimetype="application/pdf"
    )


@main.route('/apriori/download-pdf-file')
@login_required
def download_pdf_apriori_file():
    min_support = parse_parameter(request.args.get('min_support', 0.1), 0.1)
    min_confidence = parse_parameter(request.args.get('min_confidence', 0.5), 0.5)

    try:
        min_lift = float(request.args.get('min_lift', 1.0))
    except Exception:
        min_lift = 1.0

    path_file = session.get('apriori_file_path')
    nama_file = session.get('apriori_file_name', 'file_upload')

    if not path_file or not os.path.exists(path_file):
        flash('Data file sudah tidak tersedia. Silakan jalankan analisis dari file lagi sebelum mencetak PDF.', 'warning')
        return redirect(url_for('main.apriori'))

    with open(path_file, 'rb') as f:
        file_bytes = f.read()

    hasil = jalankan_apriori_dari_file(
        file_bytes=file_bytes,
        filename=nama_file,
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift
    )

    bagian = request.args.get('bagian', 'semua')
    periode = f"File — {nama_file}"

    buffer = _buat_pdf_buffer_apriori(hasil, min_support, min_confidence, min_lift, periode, bagian)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=_nama_file_pdf(bagian),
        mimetype="application/pdf"
    )


def _nama_file_pdf(bagian):
    """Nama file unduhan PDF menyesuaikan bagian yang dipilih."""
    nama = {
        'l1': 'laporan_apriori_l1.pdf',
        'l2': 'laporan_apriori_l2.pdf',
        'l3': 'laporan_apriori_l3.pdf',
        'rules': 'laporan_apriori_aturan_asosiasi.pdf',
    }
    return nama.get(bagian, 'laporan_apriori_lengkap.pdf')


def _buat_pdf_buffer_apriori(hasil, min_support, min_confidence, min_lift, periode, bagian='semua'):
    """
    Bangun isi PDF laporan Apriori. Parameter `bagian` menentukan apa yang
    dicetak:
      - 'semua' : seluruh laporan (L1 + L2 + L3 + Aturan Asosiasi) — default
      - 'l1'    : hanya Frequent 1-Itemset
      - 'l2'    : hanya Frequent 2-Itemset
      - 'l3'    : hanya Frequent 3-Itemset
      - 'rules' : hanya Aturan Asosiasi

    Dipakai bersama oleh download_pdf_apriori (sumber database) dan
    download_pdf_apriori_file (sumber file upload) supaya tidak duplikat kode.
    """
    JUDUL_BAGIAN = {
        'l1': 'Laporan Frequent 1-Itemset (L1)',
        'l2': 'Laporan Frequent 2-Itemset (L2)',
        'l3': 'Laporan Frequent 3-Itemset (L3)',
        'rules': 'Laporan Aturan Asosiasi',
        'semua': 'Laporan Hasil Analisis Apriori',
    }

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=105,
        bottomMargin=110
    )

    styles = getSampleStyleSheet()
    style_center_h3 = ParagraphStyle(
        'CenterH3Apriori', parent=styles['Heading3'], alignment=TA_CENTER
    )
    style_center_normal = ParagraphStyle(
        'CenterNormalApriori', parent=styles['Normal'], alignment=TA_CENTER
    )

    nama_penanggung_jawab = current_user.nama_lengkap if current_user.is_authenticated else 'Admin'
    judul_laporan = JUDUL_BAGIAN.get(bagian, JUDUL_BAGIAN['semua'])

    def _header_footer(canvas, doc_):
        _gambar_kop_surat_pdf(
            canvas, doc_,
            judul_laporan=judul_laporan,
            periode=periode,
            nama_penanggung_jawab=nama_penanggung_jawab
        )

    elements = []

    # Tabel ringkasan hanya ditampilkan untuk cetak "Semua" dan "Aturan
    # Asosiasi". Untuk cetak L1/L2/L3 saja, tabel ringkasan ini disembunyikan
    # sepenuhnya karena parameter di dalamnya (terutama confidence & lift)
    # tidak relevan dengan hasil frequent itemset saja.
    if bagian in ('semua', 'rules'):
        ringkasan = [
            ["Keterangan", "Nilai"],
            ["Total Transaksi", str(hasil.get("total_trx", 0))],
            ["Total Item Unik", str(hasil.get("total_item", 0))],
            ["Minimum Support", f"{min_support * 100:.2f}%"],
            ["Minimum Confidence", f"{min_confidence * 100:.2f}%"],
            ["Minimum Lift", str(min_lift)],
            ["Batas Minimum Support", f"{hasil.get('batas_support_transaksi', 0)} transaksi"],
        ]

        elements.append(_buat_tabel_pdf(ringkasan, lebar=[220, 300]))
        elements.append(Spacer(1, 16))

    if hasil.get("status") != "success":
        elements.append(Paragraph(f"<b>Pesan:</b> {hasil.get('pesan', 'Analisis gagal.')}", style_center_normal))
        doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
        buffer.seek(0)
        return buffer

    if bagian in ('semua', 'l1'):
        elements.append(Paragraph("<b>Frequent 1-Itemset (L1)</b>", style_center_h3))

        l1_data = [["No", "Menu", "Jumlah Transaksi", "Support"]]

        for i, row in enumerate(hasil.get("l1", []), start=1):
            l1_data.append([
                str(i),
                row.get("itemset", ""),
                str(row.get("jumlah", "")),
                f"{row.get('support_pct', 0)}%"
            ])

        elements.append(_buat_tabel_pdf(l1_data, lebar=[35, 360, 120, 90]))
        elements.append(Spacer(1, 16))

    if bagian in ('semua', 'l2'):
        elements.append(Paragraph("<b>Frequent 2-Itemset (L2)</b>", style_center_h3))

        l2_data = [["No", "Kombinasi Menu", "Jumlah Transaksi", "Support"]]

        for i, row in enumerate(hasil.get("l2", []), start=1):
            l2_data.append([
                str(i),
                row.get("itemset", ""),
                str(row.get("jumlah", "")),
                f"{row.get('support_pct', 0)}%"
            ])

        elements.append(_buat_tabel_pdf(l2_data, lebar=[35, 360, 120, 90]))
        elements.append(Spacer(1, 16))

    if bagian in ('semua', 'l3'):
        elements.append(Paragraph("<b>Frequent 3-Itemset (L3)</b>", style_center_h3))

        l3_rows = hasil.get("l3", [])

        if l3_rows:
            l3_data = [["No", "Kombinasi Menu", "Jumlah Transaksi", "Support"]]

            for i, row in enumerate(l3_rows, start=1):
                l3_data.append([
                    str(i),
                    row.get("itemset", ""),
                    str(row.get("jumlah", "")),
                    f"{row.get('support_pct', 0)}%"
                ])

            elements.append(_buat_tabel_pdf(l3_data, lebar=[35, 360, 120, 90]))
        else:
            elements.append(Paragraph("Tidak terdapat frequent 3-itemset yang memenuhi minimum support.", style_center_normal))

        elements.append(Spacer(1, 16))

    if bagian in ('semua', 'rules'):
        elements.append(Paragraph("<b>Aturan Asosiasi</b>", style_center_h3))

        rules_data = [[
            "No", "Jika Beli", "Maka Beli", "Support",
            "Confidence", "Lift", "Leverage", "Conviction", "Kekuatan"
        ]]

        for i, rule in enumerate(hasil.get("rules", []), start=1):
            rules_data.append([
                str(i),
                rule.get("jika_beli", ""),
                rule.get("maka_beli", ""),
                f"{rule.get('support_pct', 0)}%",
                f"{rule.get('confidence_pct', 0)}%",
                str(rule.get("lift", "")),
                str(rule.get("leverage", "")),
                str(rule.get("conviction", "")),
                rule.get("interpretasi", "")
            ])

        elements.append(_buat_tabel_pdf(
            rules_data,
            lebar=[30, 150, 150, 65, 75, 55, 65, 70, 80],
            font_size=7
        ))

        elements.append(Spacer(1, 16))
        elements.append(Paragraph("<b>Catatan:</b>", style_center_h3))
        elements.append(Paragraph(
            "Aturan asosiasi yang ditampilkan merupakan aturan yang memenuhi minimum support, "
            "minimum confidence, dan minimum lift. Nilai lift lebih dari 1 menunjukkan hubungan positif "
            "antar menu yang dibeli pelanggan.",
            style_center_normal
        ))

    doc.build(elements, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer


_NAMA_BULAN_INDO = [
    '', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'
]

# Taruh file logo kedai di sini untuk memakainya di kop surat PDF.
# Format yang didukung: .png, .jpg, .jpeg — disarankan gambar persegi
# (mis. 300x300px), latar transparan (PNG) supaya rapi di atas kertas putih.
LOKASI_LOGO_PDF = os.path.join(os.path.dirname(__file__), 'static', 'img', 'logo.png')


def _tanggal_indo(dt):
    """Format tanggal ke gaya Indonesia, mis. '13 Juli 2026'."""
    return f"{dt.day} {_NAMA_BULAN_INDO[dt.month]} {dt.year}"


def _gambar_kop_surat_pdf(canvas, doc, judul_laporan, periode, nama_penanggung_jawab='Admin', kota='Bekasi'):
    """
    Menggambar kop surat (logo, judul, periode) di bagian atas dan
    nomor halaman + blok tanda tangan di bagian bawah, otomatis di
    SETIAP halaman PDF — mengikuti format laporan formal standar.
    """
    canvas.saveState()
    lebar_halaman, tinggi_halaman = doc.pagesize
    tengah_x = lebar_halaman / 2

    # ── Logo ─────────────────────────────────────────────────
    y_logo = tinggi_halaman - 40

    if os.path.exists(LOKASI_LOGO_PDF):
        # Pakai file logo kustom kalau tersedia di LOKASI_LOGO_PDF.
        ukuran = 34
        canvas.drawImage(
            LOKASI_LOGO_PDF,
            tengah_x - ukuran / 2, y_logo - ukuran / 2,
            width=ukuran, height=ukuran,
            preserveAspectRatio=True, mask='auto'
        )
    else:
        # Fallback: monogram lingkaran otomatis kalau belum ada file logo.
        canvas.setStrokeColor(colors.HexColor("#3B2414"))
        canvas.setLineWidth(1.2)
        canvas.circle(tengah_x, y_logo, 15, stroke=1, fill=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(colors.HexColor("#3B2414"))
        canvas.drawCentredString(tengah_x, y_logo - 3.5, "CT")

    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(colors.HexColor("#3B2414"))
    canvas.drawCentredString(tengah_x, y_logo - 25, "KEDAI KOPI CING TONO")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#8B7355"))
    canvas.drawCentredString(tengah_x, y_logo - 35, "— Warkop & Ngopi Santai —")

    # ── Judul laporan & periode ─────────────────────────────
    canvas.setFont("Helvetica-Bold", 13)
    canvas.setFillColor(colors.black)
    canvas.drawCentredString(tengah_x, y_logo - 55, judul_laporan.upper())

    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(tengah_x, y_logo - 67, f"Periode: {periode}")

    canvas.setStrokeColor(colors.HexColor("#D9CDBF"))
    canvas.setLineWidth(0.6)
    canvas.line(30, y_logo - 78, lebar_halaman - 30, y_logo - 78)

    # ── Footer: nomor halaman ───────────────────────────────
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#8B7355"))
    canvas.drawRightString(lebar_halaman - 30, 95, f"Halaman {doc.page}")

    # ── Blok tanda tangan (muncul di setiap halaman) ────────
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.black)
    canvas.drawRightString(lebar_halaman - 30, 78, f"{kota}, {_tanggal_indo(datetime.now())}")
    canvas.drawRightString(lebar_halaman - 30, 66, "Penanggung Jawab,")
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawRightString(lebar_halaman - 30, 32, f"( {nama_penanggung_jawab.upper()} )")

    canvas.restoreState()


def _buat_tabel_pdf(data, lebar=None, font_size=8, gaya_tambahan=None):
    table = Table(data, colWidths=lebar, repeatRows=1)
    table.hAlign = 'CENTER'

    gaya = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8D8C3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3B2414")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFB7AE")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF7F2")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]

    if gaya_tambahan:
        gaya.extend(gaya_tambahan)

    table.setStyle(TableStyle(gaya))

    return table


@main.route('/apriori/download-template')
@login_required
def download_template_apriori():
    csv_content = (
        "transaksi_id,item\n"
        "1,Kopi Susu\n"
        "1,Roti Bakar\n"
        "1,Pisang Goreng\n"
        "2,Es Teh\n"
        "2,Kopi Hitam\n"
        "3,Kopi Susu\n"
        "3,Pisang Goreng\n"
        "4,Es Teh\n"
        "4,Roti Bakar\n"
        "5,Kopi Susu\n"
        "5,Es Teh\n"
        "5,Kopi Hitam\n"
    )

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=template_apriori.csv'}
    )


# ══════════════════════════════════════════════════════════
# MANAJEMEN MENU
# ══════════════════════════════════════════════════════════

@main.route('/menu')
@login_required
def menu():
    menus = Menu.query.order_by(Menu.kategori_id, Menu.nama).all()
    kategoris = KategoriMenu.query.all()

    return render_template(
        'menu.html',
        menus=menus,
        kategoris=kategoris,
        format_rupiah=format_rupiah
    )


@main.route('/menu/tambah', methods=['POST'])
@login_required
def menu_tambah():
    nama = request.form.get('nama', '').strip()
    harga = int(request.form.get('harga', 0))
    kategori_id = int(request.form.get('kategori_id', 0))
    deskripsi = request.form.get('deskripsi', '').strip()
    tersedia = request.form.get('tersedia') == 'on'

    if not nama or harga <= 0 or not kategori_id:
        flash('Data menu tidak lengkap.', 'danger')
        return redirect(url_for('main.menu'))

    m = Menu(
        nama=nama,
        harga=harga,
        kategori_id=kategori_id,
        deskripsi=deskripsi,
        tersedia=tersedia
    )

    db.session.add(m)
    db.session.commit()

    flash(f'Menu "{nama}" berhasil ditambahkan.', 'success')
    return redirect(url_for('main.menu'))


@main.route('/menu/edit/<int:menu_id>', methods=['POST'])
@login_required
def menu_edit(menu_id):
    m = Menu.query.get_or_404(menu_id)

    m.nama = request.form.get('nama', m.nama).strip()
    m.harga = int(request.form.get('harga', m.harga))
    m.kategori_id = int(request.form.get('kategori_id', m.kategori_id))
    m.deskripsi = request.form.get('deskripsi', '').strip()
    m.tersedia = request.form.get('tersedia') == 'on'

    db.session.commit()

    flash(f'Menu "{m.nama}" berhasil diperbarui.', 'success')
    return redirect(url_for('main.menu'))


@main.route('/menu/hapus/<int:menu_id>', methods=['POST'])
@login_required
def menu_hapus(menu_id):
    m = Menu.query.get_or_404(menu_id)
    nama = m.nama

    db.session.delete(m)
    db.session.commit()

    flash(f'Menu "{nama}" berhasil dihapus.', 'success')
    return redirect(url_for('main.menu'))


@main.route('/menu/kategori/tambah', methods=['POST'])
@login_required
def kategori_tambah():
    nama = request.form.get('nama', '').strip()

    if not nama:
        flash('Nama kategori tidak boleh kosong.', 'danger')
        return redirect(url_for('main.menu'))

    if KategoriMenu.query.filter_by(nama=nama).first():
        flash(f'Kategori "{nama}" sudah ada.', 'warning')
        return redirect(url_for('main.menu'))

    db.session.add(KategoriMenu(nama=nama))
    db.session.commit()

    flash(f'Kategori "{nama}" berhasil ditambahkan.', 'success')
    return redirect(url_for('main.menu'))


# ══════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════

@main.route('/users')
@login_required
def users():
    if current_user.role != 'admin':
        flash('Akses ditolak. Hanya admin yang dapat mengelola user.', 'danger')
        return redirect(url_for('main.beranda'))

    semua_user = User.query.order_by(User.created_at.desc()).all()

    return render_template('users.html', semua_user=semua_user)


@main.route('/users/tambah', methods=['POST'])
@login_required
def users_tambah():
    if current_user.role != 'admin':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('main.beranda'))

    username = request.form.get('username', '').strip()
    nama_lengkap = request.form.get('nama_lengkap', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'kasir')

    if not username or not nama_lengkap or not password:
        flash('Semua field wajib diisi.', 'danger')
        return redirect(url_for('main.users'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" sudah digunakan.', 'warning')
        return redirect(url_for('main.users'))

    user = User(
        username=username,
        nama_lengkap=nama_lengkap,
        password=generate_password_hash(password),
        role=role
    )

    db.session.add(user)
    db.session.commit()

    flash(f'User "{username}" berhasil ditambahkan.', 'success')
    return redirect(url_for('main.users'))


@main.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
def users_edit(user_id):
    if current_user.role != 'admin':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('main.beranda'))

    u = User.query.get_or_404(user_id)

    username_baru = request.form.get('username', '').strip()
    nama_baru = request.form.get('nama_lengkap', '').strip()
    role_baru = request.form.get('role', u.role)
    password_baru = request.form.get('password', '').strip()

    existing = User.query.filter_by(username=username_baru).first()

    if existing and existing.id != user_id:
        flash(f'Username "{username_baru}" sudah digunakan user lain.', 'warning')
        return redirect(url_for('main.users'))

    u.username = username_baru
    u.nama_lengkap = nama_baru
    u.role = role_baru

    if password_baru:
        u.password = generate_password_hash(password_baru)

    db.session.commit()

    flash(f'User "{u.username}" berhasil diperbarui.', 'success')
    return redirect(url_for('main.users'))


@main.route('/users/hapus/<int:user_id>', methods=['POST'])
@login_required
def users_hapus(user_id):
    if current_user.role != 'admin':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('main.beranda'))

    if user_id == current_user.id:
        flash('Tidak bisa menghapus akun sendiri.', 'danger')
        return redirect(url_for('main.users'))

    u = User.query.get_or_404(user_id)
    nama = u.username

    db.session.delete(u)
    db.session.commit()

    flash(f'User "{nama}" berhasil dihapus.', 'success')
    return redirect(url_for('main.users'))


@main.route('/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def users_reset_password(user_id):
    if current_user.role != 'admin':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('main.beranda'))

    u = User.query.get_or_404(user_id)
    password_baru = request.form.get('password_baru', '').strip()

    if not password_baru or len(password_baru) < 6:
        flash('Password minimal 6 karakter.', 'danger')
        return redirect(url_for('main.users'))

    u.password = generate_password_hash(password_baru)
    db.session.commit()

    flash(f'Password user "{u.username}" berhasil direset.', 'success')
    return redirect(url_for('main.users'))


# ══════════════════════════════════════════════════════════
# MANAJEMEN STOK BAHAN
# ══════════════════════════════════════════════════════════

@main.route('/stok')
@login_required
def stok():
    bahans = StokBahan.query.order_by(StokBahan.nama_bahan).all()
    menus = Menu.query.order_by(Menu.nama).all()
    resep_list = ResepMenu.query.join(Menu).order_by(Menu.nama).all()
    return render_template('stok.html', bahans=bahans, menus=menus, resep_list=resep_list)


@main.route('/stok/resep/tambah', methods=['POST'])
@login_required
def resep_tambah():
    menu_id = request.form.get('menu_id', type=int)
    bahan_id = request.form.get('bahan_id', type=int)
    jumlah_terpakai = request.form.get('jumlah_terpakai', type=float)

    if not menu_id or not bahan_id or not jumlah_terpakai or jumlah_terpakai <= 0:
        flash('Data resep tidak lengkap.', 'danger')
        return redirect(url_for('main.stok'))

    sudah_ada = ResepMenu.query.filter_by(menu_id=menu_id, bahan_id=bahan_id).first()

    if sudah_ada:
        sudah_ada.jumlah_terpakai = jumlah_terpakai
        flash('Resep sudah ada, jumlah pemakaian berhasil diperbarui.', 'success')
    else:
        r = ResepMenu(menu_id=menu_id, bahan_id=bahan_id, jumlah_terpakai=jumlah_terpakai)
        db.session.add(r)
        flash('Resep berhasil ditambahkan.', 'success')

    db.session.commit()
    return redirect(url_for('main.stok'))


@main.route('/stok/resep/hapus/<int:resep_id>', methods=['POST'])
@login_required
def resep_hapus(resep_id):
    r = ResepMenu.query.get_or_404(resep_id)
    db.session.delete(r)
    db.session.commit()

    flash('Resep berhasil dihapus.', 'success')
    return redirect(url_for('main.stok'))


@main.route('/stok/tambah', methods=['POST'])
@login_required
def stok_tambah():
    nama = request.form.get('nama_bahan', '').strip()
    satuan = request.form.get('satuan', '').strip()
    jumlah = float(request.form.get('jumlah', 0))
    min_s = float(request.form.get('minimum_stok', 0))

    if not nama or not satuan:
        flash('Data stok tidak lengkap.', 'danger')
        return redirect(url_for('main.stok'))

    b = StokBahan(
        nama_bahan=nama,
        satuan=satuan,
        jumlah=jumlah,
        minimum_stok=min_s
    )

    db.session.add(b)
    db.session.commit()

    flash(f'Bahan "{nama}" berhasil ditambahkan.', 'success')
    return redirect(url_for('main.stok'))


@main.route('/stok/edit/<int:bahan_id>', methods=['POST'])
@login_required
def stok_edit(bahan_id):
    b = StokBahan.query.get_or_404(bahan_id)

    b.nama_bahan = request.form.get('nama_bahan', b.nama_bahan).strip()
    b.satuan = request.form.get('satuan', b.satuan).strip()
    b.jumlah = float(request.form.get('jumlah', b.jumlah))
    b.minimum_stok = float(request.form.get('minimum_stok', b.minimum_stok))
    b.updated_at = datetime.now()

    db.session.commit()

    flash(f'Stok "{b.nama_bahan}" berhasil diperbarui.', 'success')
    return redirect(url_for('main.stok'))


@main.route('/stok/hapus/<int:bahan_id>', methods=['POST'])
@login_required
def stok_hapus(bahan_id):
    b = StokBahan.query.get_or_404(bahan_id)
    nama = b.nama_bahan

    db.session.delete(b)
    db.session.commit()

    flash(f'Bahan "{nama}" berhasil dihapus.', 'success')
    return redirect(url_for('main.stok'))


@main.route('/stok/restok/<int:bahan_id>', methods=['POST'])
@login_required
def stok_restok(bahan_id):
    b = StokBahan.query.get_or_404(bahan_id)
    tambah = float(request.form.get('jumlah_tambah', 0))

    if tambah <= 0:
        flash('Jumlah tambah stok harus lebih dari 0.', 'danger')
        return redirect(url_for('main.stok'))

    b.jumlah += tambah
    b.updated_at = datetime.now()

    db.session.commit()

    flash(f'Stok "{b.nama_bahan}" berhasil ditambah {tambah} {b.satuan}.', 'success')
    return redirect(url_for('main.stok'))