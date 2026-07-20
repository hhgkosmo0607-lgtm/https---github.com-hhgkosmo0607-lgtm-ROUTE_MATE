"""외부 API 응답 캐시 (설계서 12.2절).

프로세스 내 TTL 캐시 — 반복 호출을 줄여 공개 서버 정책 준수와 응답 속도를 함께
확보한다. 다중 워커 배포에서는 워커별로 독립 캐시가 되므로, 적중률을 높이려면
Redis 등 공유 저장소로의 교체가 확장 경로다(12.4절).
"""

import threading
import time


class TTLCache:
    def __init__(self, maxsize=500):
        self.maxsize = maxsize
        self._store = {}  # key -> (expires_at, value)
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key, value, ttl):
        with self._lock:
            if len(self._store) >= self.maxsize:
                # 만료 임박 순으로 10%를 비운다 (단순 eviction)
                for old_key, _ in sorted(self._store.items(), key=lambda kv: kv[1][0])[
                    : max(1, self.maxsize // 10)
                ]:
                    del self._store[old_key]
            self._store[key] = (time.monotonic() + ttl, value)

    def get_or_set(self, key, ttl, producer):
        value = self.get(key)
        if value is not None:
            return value
        value = producer()
        if value is not None:
            self.set(key, value, ttl)
        return value
