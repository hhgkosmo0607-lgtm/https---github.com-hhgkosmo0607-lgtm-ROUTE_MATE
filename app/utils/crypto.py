"""알레르기 정보 애플리케이션 레벨 AES-256 암호화 (설계서 11.3절).

건강 관련 민감정보이므로 저장 전 AES-256-GCM으로 암호화하고, 조회 시에만
복호화한다. 운영 환경은 ALLERGY_ENCRYPTION_KEY 환경변수(base64, 32바이트)로
실제 키를 주입해야 한다 — 미설정 시 개발용 고정 키로 폴백한다(운영 사용 금지).
"""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

_DEV_KEY_PASSPHRASE = "routemate-dev-only-change-in-production"


def _get_key():
    key_b64 = None
    if current_app:
        key_b64 = current_app.config.get("ALLERGY_ENCRYPTION_KEY")
    if not key_b64:
        return hashlib.sha256(_DEV_KEY_PASSPHRASE.encode()).digest()
    return base64.urlsafe_b64decode(key_b64)


def encrypt_json(value):
    if value is None:
        return None
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(12)
    plaintext = json.dumps(value, ensure_ascii=False).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_json(token):
    if token is None:
        return None
    aesgcm = AESGCM(_get_key())
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext.decode("utf-8"))
