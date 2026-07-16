from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address)

# BIGINT AUTO_INCREMENT PK (설계서 6.1) on every dialect except SQLite, where
# only an "INTEGER PRIMARY KEY" column aliases the rowid and autoincrements.
BigIntPK = db.BigInteger().with_variant(db.Integer, "sqlite")
