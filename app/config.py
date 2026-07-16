import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "route_mate.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"

    WTF_CSRF_HEADERS = ["X-CSRF-Token"]

    # 8.4절/11.2절: 로그인 10/분(IP), AI 추천 3/분(사용자). Redis 없는 환경은
    # in-memory 저장소로 폴백(단일 프로세스 한정으로만 유효 — NFR-08 수평 확장 시 REDIS_URL 필요).
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")

    # 11.3절: PROFILE.allergy 애플리케이션 레벨 AES-256 암호화 키(base64, 32바이트).
    # 운영 환경에서는 반드시 환경변수로 실제 키를 주입해야 한다.
    ALLERGY_ENCRYPTION_KEY = os.environ.get("ALLERGY_ENCRYPTION_KEY")

    # 8.1/8.2절: OpenStreetMap(Nominatim+OSRM) 공개 데모 서버 어댑터.
    # 키 불필요·무료지만 "합리적 비상업 사용" 정책 — 테스트/수업용으로 사용한다.
    MAP_ADAPTER_ENABLED = os.environ.get("MAP_ADAPTER_ENABLED", "true").lower() == "true"
    MAP_CONTACT_EMAIL = os.environ.get("MAP_CONTACT_EMAIL")  # Nominatim/OSRM User-Agent에 포함 권장


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_SECRET_KEY = "test-csrf-secret"
    RATELIMIT_ENABLED = True
    MAP_ADAPTER_ENABLED = False  # 테스트는 외부 네트워크 호출 없이 Haversine만 사용
