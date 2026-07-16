from datetime import datetime

from flask_login import UserMixin

from ..extensions import BigIntPK, bcrypt, db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "USER"

    user_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nickname = db.Column(db.String(30), nullable=False)
    login_fail_cnt = db.Column(db.SmallInteger, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")

    def get_id(self):
        return str(self.user_id)

    @property
    def is_active(self):
        return self.deleted_at is None

    def set_password(self, raw_password):
        self.password_hash = bcrypt.generate_password_hash(raw_password, rounds=12).decode("utf-8")

    def check_password(self, raw_password):
        return bcrypt.check_password_hash(self.password_hash, raw_password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
