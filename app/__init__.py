import logging
import secrets

from flask import Flask, g

from .config import Config
from .extensions import bcrypt, csrf, db, limiter, login_manager, migrate
from .utils.response import error_response


def _configure_audit_logging():
    """11.4절 감사 로깅 — 표준 출력에 JSON 라인으로 남긴다 (14.4절 구조화 로그)."""
    audit_logger = logging.getLogger("routemate.audit")
    audit_logger.setLevel(logging.INFO)
    if not audit_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    _configure_audit_logging()

    with app.app_context():
        from . import models  # noqa: F401  (registers models on db.metadata)

    @login_manager.unauthorized_handler
    def unauthorized():
        return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

    from .controllers.auth_controller import auth_bp
    from .controllers.checklist_controller import checklist_bp
    from .controllers.place_controller import place_bp
    from .controllers.planb_controller import planb_bp
    from .controllers.recommendation_controller import recommendation_bp
    from .controllers.schedule_controller import schedule_bp
    from .controllers.shared_controller import shared_bp
    from .controllers.trip_controller import trip_bp
    from .controllers.user_controller import user_bp
    from .controllers.views import views_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/users")
    app.register_blueprint(trip_bp, url_prefix="/api/trips")
    app.register_blueprint(schedule_bp, url_prefix="/api/schedules")
    app.register_blueprint(recommendation_bp, url_prefix="/api/recommendations")
    app.register_blueprint(planb_bp, url_prefix="/api/planb")
    app.register_blueprint(checklist_bp, url_prefix="/api/checklist")
    app.register_blueprint(shared_bp, url_prefix="/api/shared")
    app.register_blueprint(place_bp, url_prefix="/api/places")
    app.register_blueprint(views_bp)

    @app.get("/api/csrf-token")
    def csrf_token():
        from flask_wtf.csrf import generate_csrf

        return {"success": True, "data": {"csrf_token": generate_csrf()}, "error": None}

    @app.get("/healthz")
    def healthz():
        # 14.4절: 웹·DB 점검 — 모니터링이 1분 간격으로 조회
        try:
            from sqlalchemy import text

            db.session.execute(text("SELECT 1"))
            db_status = "ok"
            status_code = 200
        except Exception:
            db_status = "error"
            status_code = 503
        return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}, status_code

    @app.before_request
    def set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def inject_csp_nonce():
        return {"csp_nonce": lambda: g.get("csp_nonce", "")}

    @app.after_request
    def set_security_headers(response):
        # 11.2절 XSS 대응: CSP 헤더. 인라인 <script>는 요청별 nonce로만 허용한다.
        # 인라인 style 속성은 페이지 전반에서 사용 중이라 style-src는 unsafe-inline을 허용한다
        # (스타일 인젝션은 스크립트 인젝션보다 위험도가 낮은 절충).
        nonce = g.get("csp_nonce", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://*.tile.openstreetmap.org; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.errorhandler(404)
    def not_found(_e):
        return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return error_response("FORBIDDEN", "CSRF 토큰이 유효하지 않습니다.", 403)

    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def rate_limit_error(_e):
        return error_response("RATE_LIMITED", "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.", 429)

    return app
