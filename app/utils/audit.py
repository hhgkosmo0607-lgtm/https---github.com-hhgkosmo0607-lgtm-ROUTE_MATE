"""감사 로깅 (설계서 11.4절).

로그인/로그아웃/실패, 권한 거부, 여행 삭제, 회원 탈퇴, Plan B 발동을 기록한다.
비밀번호·세션 토큰·알레르기 정보는 절대 남기지 않는다.
"""

import json
import logging
from datetime import datetime, timezone

from flask import has_request_context, request

_logger = logging.getLogger("routemate.audit")


def log_event(event, user_id=None, result="SUCCESS", **extra):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user_id": user_id,
        "ip": request.remote_addr if has_request_context() else None,
        "result": result,
    }
    entry.update(extra)
    _logger.info(json.dumps(entry, ensure_ascii=False))
