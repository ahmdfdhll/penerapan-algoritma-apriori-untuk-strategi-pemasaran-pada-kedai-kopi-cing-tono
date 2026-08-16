from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager


# ══════════════════════════════════════════════════════════
#  USER LOADER
# ══════════════════════════════════════════════════════════
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ══════════════════════════════════════════════════════════
#  USER
# ══════════════════════════════════════════════════════════
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(50), unique=True, nullable=False)
    password     = db.Column(db.String(256), nullable=False)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    role         = db.Column(db.Enum('admin', 'kasir', 'owner'), default='kasir', nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    transaksis = db.relationship('Transaksi', backref='kasir', lazy=True)

    def __repr__(self):
        return f'<User {self.username}>'


# ══════════════════════════════════════════════════════════
#  KATEGORI MENU
# ══════════════════════════════════════════════════════════
class KategoriMenu(db.Model):
    __tablename__ = 'kategori_menu'

    id   = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(50), unique=True, nullable=False)

    menus = db.relationship('Menu', backref='kategori', lazy=True)

    def __repr__(self):
        return f'<Kategori {self.nama}>'


# ══════════════════════════════════════════════════════════
#  MENU
# ══════════════════════════════════════════════════════════
class Menu(db.Model):
    __tablename__ = 'menu'

    id           = db.Column(db.Integer, primary_key=True)
    nama         = db.Column(db.String(100), nullable=False)
    harga        = db.Column(db.Integer, nullable=False)           # dalam Rupiah
    kategori_id  = db.Column(db.Integer, db.ForeignKey('kategori_menu.id'), nullable=False)
    deskripsi    = db.Column(db.Text, default='')
    tersedia     = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    detail_transaksis = db.relationship('DetailTransaksi', backref='menu', lazy=True)

    def __repr__(self):
        return f'<Menu {self.nama}>'


# ══════════════════════════════════════════════════════════
#  STOK BAHAN
# ══════════════════════════════════════════════════════════
class StokBahan(db.Model):
    __tablename__ = 'stok_bahan'

    id            = db.Column(db.Integer, primary_key=True)
    nama_bahan    = db.Column(db.String(100), nullable=False)
    satuan        = db.Column(db.String(20), nullable=False)   # gram, ml, pcs, dll
    jumlah        = db.Column(db.Float, default=0, nullable=False)
    minimum_stok  = db.Column(db.Float, default=0, nullable=False)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_rendah(self):
        return self.jumlah <= self.minimum_stok

    def __repr__(self):
        return f'<StokBahan {self.nama_bahan}>'


# ══════════════════════════════════════════════════════════
#  RESEP MENU (Bill of Materials: bahan apa & berapa banyak
#  terpakai untuk membuat 1 porsi menu tertentu)
# ══════════════════════════════════════════════════════════
class ResepMenu(db.Model):
    __tablename__ = 'resep_menu'

    id               = db.Column(db.Integer, primary_key=True)
    menu_id          = db.Column(db.Integer, db.ForeignKey('menu.id'), nullable=False)
    bahan_id         = db.Column(db.Integer, db.ForeignKey('stok_bahan.id'), nullable=False)
    jumlah_terpakai  = db.Column(db.Float, nullable=False)   # per 1 porsi menu

    menu  = db.relationship('Menu', backref=db.backref('resep', lazy=True, cascade='all, delete-orphan'))
    bahan = db.relationship('StokBahan', backref=db.backref('dipakai_di', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<ResepMenu menu={self.menu_id} bahan={self.bahan_id}>'


# ══════════════════════════════════════════════════════════
#  TRANSAKSI (Header)
# ══════════════════════════════════════════════════════════
class Transaksi(db.Model):
    __tablename__ = 'transaksi'

    id           = db.Column(db.Integer, primary_key=True)
    kode         = db.Column(db.String(20), unique=True, nullable=False)   # TRX-YYYYMMDD-0001
    tanggal      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    total        = db.Column(db.Integer, nullable=False)
    bayar        = db.Column(db.Integer, nullable=False)
    kembalian    = db.Column(db.Integer, nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    catatan      = db.Column(db.Text, default='')

    details = db.relationship('DetailTransaksi', backref='transaksi', lazy=True,
                              cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Transaksi {self.kode}>'


# ══════════════════════════════════════════════════════════
#  DETAIL TRANSAKSI (Line Items)
# ══════════════════════════════════════════════════════════
class DetailTransaksi(db.Model):
    __tablename__ = 'detail_transaksi'

    id           = db.Column(db.Integer, primary_key=True)
    transaksi_id = db.Column(db.Integer, db.ForeignKey('transaksi.id'), nullable=False)
    menu_id      = db.Column(db.Integer, db.ForeignKey('menu.id'), nullable=False)
    jumlah       = db.Column(db.Integer, nullable=False)
    harga_satuan = db.Column(db.Integer, nullable=False)
    subtotal     = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<Detail trx={self.transaksi_id} menu={self.menu_id}>'