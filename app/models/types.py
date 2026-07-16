from sqlalchemy.types import Text, TypeDecorator

from ..utils.crypto import decrypt_json, encrypt_json


class EncryptedJSON(TypeDecorator):
    """JSON 값을 AES-256-GCM으로 암호화해 저장하는 컬럼 타입 (11.3절)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_json(value)

    def process_result_value(self, value, dialect):
        return decrypt_json(value)
