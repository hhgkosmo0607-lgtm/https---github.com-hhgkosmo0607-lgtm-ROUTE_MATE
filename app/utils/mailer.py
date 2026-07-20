"""메일 발송 — SMTP 설정(.env) 시 실발송, 미설정 시 서버 로그로 출력(개발 모드).

비밀번호 재설정 등 트랜잭션 메일 용도. 실서비스 전 SMTP_HOST 등을 반드시 설정한다.
"""

import logging
import smtplib
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to, subject, body):
    host = current_app.config.get("SMTP_HOST")
    if not host:
        # 개발 모드: 실제 발송 대신 로그로 출력 (모듈 로거는 루트 레벨에 걸러질 수 있어 둘 다 남긴다)
        message = f"[DEV MAIL] to={to} subject={subject!r}\n{body}"
        logger.info(message)
        current_app.logger.info(message)
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = current_app.config.get("SMTP_FROM", "noreply@routemate.local")
    msg["To"] = to

    port = int(current_app.config.get("SMTP_PORT", 587))
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.starttls()
        user = current_app.config.get("SMTP_USER")
        if user:
            server.login(user, current_app.config.get("SMTP_PASSWORD", ""))
        server.sendmail(msg["From"], [to], msg.as_string())
