from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db           = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Extensions ─────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view      = 'main.login'
    login_manager.login_message   = 'Silakan login terlebih dahulu.'
    login_manager.login_message_category = 'warning'

    # ── Blueprints ──────────────────────────────────────
    from app.routes import main
    app.register_blueprint(main)

    # ── Create tables if not exists ─────────────────────
    with app.app_context():
        db.create_all()
        _seed_default_user()

    return app


def _seed_default_user():
    """Buat akun admin default jika belum ada."""
    from app.models import User
    from werkzeug.security import generate_password_hash
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            nama_lengkap='Administrator',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
