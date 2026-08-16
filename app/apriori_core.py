"""
apriori_core.py
~~~~~~~~~~~~~~~
Implementasi algoritma Apriori menggunakan library mlxtend.

Output yang dikirim ke template:
1. Frequent 1-Itemset (L1)
2. Frequent 2-Itemset (L2)
3. Frequent 3-Itemset (L3)
4. Seluruh kombinasi 2 menu
5. Seluruh kombinasi 3 menu
6. Association rules
"""

import io
from itertools import combinations
from collections import Counter

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
from sqlalchemy import func

from app import db
from app.models import Transaksi, DetailTransaksi, Menu


# ══════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════

def normalisasi_parameter(value, default):
    """
    Supaya input aman:
    - 0.1 tetap 0.1
    - 10 dianggap 10%, diubah menjadi 0.10
    """
    try:
        angka = float(value)
    except Exception:
        return default

    if angka > 1:
        angka = angka / 100

    return angka


def _format_itemset(items):
    return ", ".join(sorted(list(items)))


def _interpretasi_lift(lift):
    if lift >= 3:
        return "Sangat Kuat"
    elif lift > 1:
        return "Kuat"
    elif lift == 1:
        return "Independen"
    return "Negatif"


# ══════════════════════════════════════════════════════════
# AMBIL DATA TRANSAKSI DATABASE
# ══════════════════════════════════════════════════════════

def ambil_data_transaksi(tgl_mulai=None, tgl_akhir=None):
    query = db.session.query(
        DetailTransaksi.transaksi_id,
        Menu.nama
    ).join(
        Menu, DetailTransaksi.menu_id == Menu.id
    ).join(
        Transaksi, DetailTransaksi.transaksi_id == Transaksi.id
    )

    if tgl_mulai:
        query = query.filter(Transaksi.tanggal >= tgl_mulai)

    if tgl_akhir:
        query = query.filter(Transaksi.tanggal < tgl_akhir)

    rows = query.order_by(DetailTransaksi.transaksi_id).all()

    keranjang = {}

    for transaksi_id, nama_menu in rows:
        if nama_menu:
            keranjang.setdefault(transaksi_id, []).append(nama_menu)

    transactions = [
        sorted(set(items))
        for items in keranjang.values()
        if items
    ]

    return transactions, len(transactions)


# ══════════════════════════════════════════════════════════
# HITUNG SEMUA KOMBINASI
# ══════════════════════════════════════════════════════════

def hitung_semua_kombinasi(transactions, panjang, total_trx, min_support):
    counter = Counter()

    for items in transactions:
        items = sorted(set(items))

        if len(items) >= panjang:
            for combo in combinations(items, panjang):
                counter[combo] += 1

    hasil = []

    for combo, jumlah in counter.items():
        support = jumlah / total_trx if total_trx else 0

        hasil.append({
            "kombinasi": ", ".join(combo),
            "jumlah": int(jumlah),
            "support": round(support * 100, 2),
            "support_raw": round(support, 4),
            "status": "Lolos" if support >= min_support else "Tidak Lolos"
        })

    hasil.sort(key=lambda x: x["jumlah"], reverse=True)

    return hasil


# ══════════════════════════════════════════════════════════
# FORMAT OUTPUT
# ══════════════════════════════════════════════════════════

def format_itemsets(df, total_trx):
    hasil = []

    if df is None or df.empty:
        return hasil

    for _, row in df.iterrows():
        jumlah = int(round(float(row["support"]) * total_trx))

        hasil.append({
            "itemsets": sorted(list(row["itemsets"])),
            "itemset": _format_itemset(row["itemsets"]),
            "jumlah": jumlah,
            "support": round(float(row["support"]), 4),
            "support_pct": round(float(row["support"]) * 100, 2),
            "length": int(row["length"]),
            "status": "Lolos"
        })

    return hasil


def format_rules(df):
    hasil = []

    if df is None or df.empty:
        return hasil

    for _, row in df.iterrows():
        conviction = row.get("conviction", 0)

        if pd.isna(conviction):
            conviction_value = 0
        elif conviction == float("inf"):
            conviction_value = 999.0
        else:
            conviction_value = round(float(conviction), 4)

        lift = float(row["lift"])

        hasil.append({
            "antecedents": sorted(list(row["antecedents"])),
            "consequents": sorted(list(row["consequents"])),
            "jika_beli": _format_itemset(row["antecedents"]),
            "maka_beli": _format_itemset(row["consequents"]),
            "support": round(float(row["support"]), 4),
            "support_pct": round(float(row["support"]) * 100, 2),
            "confidence": round(float(row["confidence"]), 4),
            "confidence_pct": round(float(row["confidence"]) * 100, 2),
            "lift": round(lift, 4),
            "leverage": round(float(row.get("leverage", 0)), 4),
            "conviction": conviction_value,
            "interpretasi": _interpretasi_lift(lift),
            "kekuatan": _interpretasi_lift(lift)
        })

    return hasil


# ══════════════════════════════════════════════════════════
# PIPELINE APRIORI
# ══════════════════════════════════════════════════════════

def _pipeline_apriori(
    transactions,
    total_trx,
    min_support,
    min_confidence,
    min_lift
):
    min_support = normalisasi_parameter(min_support, 0.1)
    min_confidence = normalisasi_parameter(min_confidence, 0.5)

    try:
        min_lift = float(min_lift)
    except Exception:
        min_lift = 1.0

    params = {
        "min_support": min_support,
        "min_confidence": min_confidence,
        "min_lift": min_lift
    }

    if total_trx < 1:
        return {
            "status": "error",
            "pesan": "Tidak ada data transaksi.",
            "total_trx": total_trx,
            "total_item": 0,
            "batas_support_transaksi": 0,
            "frequent_itemsets": [],
            "l1": [],
            "l2": [],
            "l3": [],
            "semua_kombinasi_2": [],
            "semua_kombinasi_3": [],
            "rules": [],
            "params": params
        }

    te = TransactionEncoder()
    te_array = te.fit(transactions).transform(transactions)
    df = pd.DataFrame(te_array, columns=te.columns_)

    total_item = len(te.columns_)
    batas_support_transaksi = int(round(min_support * total_trx))

    # Kandidat mentah 2-itemset tidak ditampilkan agar tampilan tidak penuh.
    # Yang dipakai untuk hasil utama adalah L2 yang lolos minimum support.
    semua_kombinasi_2 = []

    # Kandidat 3-itemset tetap dihitung hanya untuk cadangan tampilan K3,
    # tetapi dibatasi maksimal 3 kombinasi teratas supaya tidak muncul ribuan data.
    semua_kombinasi_3 = hitung_semua_kombinasi(
        transactions=transactions,
        panjang=3,
        total_trx=total_trx,
        min_support=min_support
    )[:3]

    try:
        frequent_itemsets = apriori(
            df,
            min_support=min_support,
            use_colnames=True,
            max_len=4
        )
    except Exception as e:
        return {
            "status": "error",
            "pesan": f"Gagal menjalankan Apriori: {str(e)}",
            "total_trx": total_trx,
            "total_item": total_item,
            "batas_support_transaksi": batas_support_transaksi,
            "frequent_itemsets": [],
            "l1": [],
            "l2": [],
            "l3": [],
            "semua_kombinasi_2": semua_kombinasi_2,
            "semua_kombinasi_3": semua_kombinasi_3,
            "rules": [],
            "params": params
        }

    if frequent_itemsets.empty:
        return {
            "status": "error",
            "pesan": f"Tidak ada frequent itemset dengan min_support {min_support * 100:.2f}%.",
            "total_trx": total_trx,
            "total_item": total_item,
            "batas_support_transaksi": batas_support_transaksi,
            "frequent_itemsets": [],
            "l1": [],
            "l2": [],
            "l3": [],
            "semua_kombinasi_2": semua_kombinasi_2,
            "semua_kombinasi_3": semua_kombinasi_3,
            "rules": [],
            "params": params
        }

    frequent_itemsets["length"] = frequent_itemsets["itemsets"].apply(len)

    frequent_itemsets = frequent_itemsets.sort_values(
        by=["length", "support"],
        ascending=[True, False]
    )

    l1_df = frequent_itemsets[frequent_itemsets["length"] == 1].copy()
    l2_df = frequent_itemsets[frequent_itemsets["length"] == 2].copy()
    l3_df = frequent_itemsets[frequent_itemsets["length"] == 3].copy()

    try:
        rules_df = association_rules(
            frequent_itemsets,
            metric="confidence",
            min_threshold=min_confidence
        )

        # Filter minimum lift
        rules_df = rules_df[rules_df["lift"] >= min_lift].copy()

        if not rules_df.empty:
            # Ambil hanya aturan 1 menu -> 1 menu
            # Supaya tidak muncul aturan gabungan seperti A, B -> C
            rules_df["antecedent_len"] = rules_df["antecedents"].apply(len)
            rules_df["consequent_len"] = rules_df["consequents"].apply(len)

            rules_df = rules_df[
                (rules_df["antecedent_len"] == 1) &
                (rules_df["consequent_len"] == 1)
            ].copy()

        if not rules_df.empty:
            # Hilangkan aturan bolak-balik.
            # Contoh: A -> B dan B -> A dianggap pasangan yang sama.
            # Yang disimpan hanya satu arah terbaik berdasarkan confidence, lift, dan support.
            def pasangan_tanpa_arah(row):
                a = list(row["antecedents"])[0]
                b = list(row["consequents"])[0]
                return tuple(sorted([a, b]))

            rules_df["pair_key"] = rules_df.apply(pasangan_tanpa_arah, axis=1)

            rules_df = rules_df.sort_values(
                by=["confidence", "lift", "support"],
                ascending=[False, False, False]
            )

            rules_df = rules_df.drop_duplicates(
                subset=["pair_key"],
                keep="first"
            ).copy()

            rules_df = rules_df.drop(
                columns=["pair_key", "antecedent_len", "consequent_len"],
                errors="ignore"
            )

            rules_df = rules_df.sort_values(
                by=["lift", "confidence", "support"],
                ascending=[False, False, False]
            )

    except Exception:
        rules_df = pd.DataFrame()

    fi_list = format_itemsets(frequent_itemsets, total_trx)

    return {
        "status": "success",
        "pesan": f"Berhasil menganalisis {total_trx} transaksi.",
        "total_trx": total_trx,
        "total_item": total_item,
        "batas_support_transaksi": batas_support_transaksi,
        "frequent_itemsets": fi_list,
        "l1": format_itemsets(l1_df, total_trx),
        "l2": format_itemsets(l2_df, total_trx),
        "l3": format_itemsets(l3_df, total_trx),
        "semua_kombinasi_2": semua_kombinasi_2,
        "semua_kombinasi_3": semua_kombinasi_3,
        "rules": format_rules(rules_df),
        "params": params
    }


# ══════════════════════════════════════════════════════════
# APRIORI DATABASE
# ══════════════════════════════════════════════════════════

def jalankan_apriori(
    min_support=0.1,
    min_confidence=0.5,
    min_lift=1.0,
    tgl_mulai=None,
    tgl_akhir=None
):
    transactions, total_trx = ambil_data_transaksi(tgl_mulai, tgl_akhir)

    hasil = _pipeline_apriori(
        transactions=transactions,
        total_trx=total_trx,
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift
    )

    hasil["sumber"] = "database"
    return hasil


# ══════════════════════════════════════════════════════════
# FILE UPLOAD
# ══════════════════════════════════════════════════════════

def ambil_data_dari_file(file_bytes, filename):
    fname = filename.lower()

    try:
        if fname.endswith(".csv"):
            df = None

            for sep in [",", ";", "\t", "|"]:
                try:
                    temp = pd.read_csv(io.BytesIO(file_bytes), sep=sep)
                    if len(temp.columns) > 1:
                        df = temp
                        break
                except Exception:
                    continue

            if df is None:
                df = pd.read_csv(io.BytesIO(file_bytes))

        elif fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            raise ValueError("Format file tidak didukung. Gunakan CSV atau Excel.")
    except Exception as e:
        raise ValueError(f"Gagal membaca file: {str(e)}")

    if df.empty:
        raise ValueError("File kosong atau tidak memiliki data.")

    df.columns = [str(c).strip().lower() for c in df.columns]
    cols = df.columns.tolist()

    id_candidates = [
        "transaksi_id", "id", "no", "order_id", "invoice",
        "no_transaksi", "kode", "nomor", "transaction_id",
        "kode_transaksi"
    ]

    item_candidates = [
        "item", "nama_item", "produk", "menu", "nama_menu",
        "nama_produk", "product", "barang", "nama_barang",
        "items", "product_name", "menu_name"
    ]

    id_cols = [c for c in cols if c in id_candidates]
    item_cols = [c for c in cols if c in item_candidates]

    transactions = []

    if id_cols and item_cols:
        id_col = id_cols[0]
        item_col = item_cols[0]

        df[id_col] = df[id_col].astype(str).str.strip()
        df[item_col] = df[item_col].astype(str).str.strip()

        df = df[
            df[item_col].notna()
            & (df[item_col] != "")
            & (df[item_col].str.lower() != "nan")
        ]

        keranjang = {}

        for _, row in df.iterrows():
            trx_id = row[id_col]
            item = row[item_col]

            if item:
                keranjang.setdefault(trx_id, []).append(item)

        transactions = [
            sorted(set(items))
            for items in keranjang.values()
            if items
        ]

    elif id_cols and "items" in cols:
        items_col = "items"

        for _, row in df.iterrows():
            raw = str(row[items_col])
            items = [i.strip() for i in raw.split(",") if i.strip()]
            if items:
                transactions.append(sorted(set(items)))

    else:
        transactions = _parse_wide(df)

    if not transactions:
        raise ValueError("Tidak ada transaksi valid yang dapat dianalisis.")

    return transactions, len(transactions)


def _parse_wide(df):
    transactions = []

    for _, row in df.iterrows():
        items = []

        for col, val in row.items():
            if pd.isna(val):
                continue

            val_str = str(val).strip()

            if val_str == "" or val_str.lower() in ("nan", "none", "-"):
                continue

            if val_str in ("1", "1.0", "true", "True", "ya", "Ya"):
                items.append(str(col).strip())
            elif not val_str.replace(".", "", 1).isdigit():
                items.append(val_str)

        if items:
            transactions.append(sorted(set(items)))

    return transactions


def jalankan_apriori_dari_file(
    file_bytes,
    filename,
    min_support=0.1,
    min_confidence=0.5,
    min_lift=1.0
):
    try:
        transactions, total_trx = ambil_data_dari_file(file_bytes, filename)
    except ValueError as e:
        return {
            "status": "error",
            "pesan": str(e),
            "total_trx": 0,
            "total_item": 0,
            "batas_support_transaksi": 0,
            "frequent_itemsets": [],
            "l1": [],
            "l2": [],
            "l3": [],
            "semua_kombinasi_2": [],
            "semua_kombinasi_3": [],
            "rules": [],
            "sumber": "file",
            "params": {
                "min_support": min_support,
                "min_confidence": min_confidence,
                "min_lift": min_lift
            }
        }

    hasil = _pipeline_apriori(
        transactions=transactions,
        total_trx=total_trx,
        min_support=min_support,
        min_confidence=min_confidence,
        min_lift=min_lift
    )

    hasil["sumber"] = f"file:{filename}"
    return hasil


# ══════════════════════════════════════════════════════════
# STATISTIK ITEM POPULER
# ══════════════════════════════════════════════════════════

def statistik_item_populer(limit=10):
    hasil = db.session.query(
        Menu.nama,
        func.sum(DetailTransaksi.jumlah).label("total_terjual"),
        func.count(DetailTransaksi.transaksi_id).label("frekuensi_transaksi")
    ).join(
        DetailTransaksi, Menu.id == DetailTransaksi.menu_id
    ).group_by(
        Menu.id, Menu.nama
    ).order_by(
        func.sum(DetailTransaksi.jumlah).desc()
    ).limit(limit).all()

    return [
        {
            "nama": r.nama,
            "total_terjual": int(r.total_terjual or 0),
            "frekuensi_transaksi": int(r.frekuensi_transaksi or 0)
        }
        for r in hasil
    ]