import os

class Config:
    # ── Flask ──────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY', 'kedai-cing-tono-secret-2024')

    # ── MySQL via PyMySQL ──────────────────────────────
    MYSQL_HOST     = os.environ.get('MYSQL_HOST',     'localhost')
    MYSQL_PORT     = int(os.environ.get('MYSQL_PORT', 3306))
    MYSQL_USER     = os.environ.get('MYSQL_USER',     'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB',       'kedai_kopi_cing_tono')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SSL untuk database online seperti Aiven
    if MYSQL_HOST != 'localhost':
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                'ssl': {}
            }
        }

    # ── Apriori defaults ───────────────────────────────
    APRIORI_MIN_SUPPORT    = 0.1
    APRIORI_MIN_CONFIDENCE = 0.5
    APRIORI_MIN_LIFT       = 1.0
