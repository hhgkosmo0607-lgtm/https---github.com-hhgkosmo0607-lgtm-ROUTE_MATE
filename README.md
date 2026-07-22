# RouteMate

AI 기반 여행 경로 설계 통합 웹서비스 — 장소 선택부터 경로 최적화, 돌발 상황 대응(Plan B)까지 하나의 흐름으로 해결하는 지도 기반 여행 설계 플랫폼.

> 상세 설계: [설계서.md](설계서.md) (v1.2, 구현 반영 개정) · 원본: `RouteMate_설계서 .docx`

## 핵심 기능 (구현 완료)

| 기능 | 설명 |
|---|---|
| **경로 자동 최적화** | Google OR-Tools VRPTW 솔버로 Day 배치와 방문 순서를 동시 최적화. NN+2-opt 휴리스틱 대비 이동시간 3~27% 단축(실측), 솔버 장애 시 휴리스틱 자동 폴백 |
| **지도 기반 설계** | Leaflet+OpenStreetMap. 검색·지도·일정 3단 화면, 확대 시 주변 POI 점 표시(클릭→일정 추가), 지도 화면 내 카테고리·상호 검색("카페", "스타벅스"…), 동네 주변 탐색 패널 |
| **실경로 이동시간** | OSRM(자동차/도보 프로파일) 실도로 기준 거리행렬, 실패 시 Haversine 근사 + "근사치" 표기 |
| **일정 편집** | 순서 이동·Day 이동·미배치 보관함, 체류시간 수정, 일정 잠금 — 변경 시 영향 Day만 부분 재계산 |
| **맞춤 추천** | 여행 프로필(취향·알레르기·예산) 하드 필터 + 스코어링. `GEMINI_API_KEY` 설정 시 Gemini가 적합도 점수·자연어 사유를 생성, 미설정/실패 시 규칙 기반 스코어링으로 자동 폴백. 추천 수락/거절 이력 기록 |
| **Plan B** | 일정별 대체 장소 등록(웨이팅/휴무/우천/수동) → 발동 → 재구성 미리보기 → 승인/거절 → 되돌리기. 활동시간 초과 시 명시적 승인 요구 |
| **부가 기능** | 체크리스트(기본 템플릿), 예산 관리(카테고리별 집계·시각화), 읽기 전용 공유 링크, 동반자 초대(OWNER/EDITOR/VIEWER), 여행 복제 |
| **보안** | bcrypt(cost 12), 로그인 잠금, 비밀번호 재설정(1시간 토큰·자동 무효화), CSRF, CSP(nonce), 레이트 리밋, 알레르기 정보 AES-256-GCM 암호화 저장, JSON 감사 로깅, 오픈 리다이렉트 차단, 비멤버 404(존재 은닉) |
| **운영** | 외부 API 응답 TTL 캐시(행렬 7일·검색 24h·POI 1h), healthz DB 점검, 이용약관·개인정보처리방침 페이지, 빈 시간 자동 감지→"AI로 채우기"(FR-303) |

## 기술 스택

- **Backend**: Python / Flask 3 · SQLAlchemy 2 · SQLite(개발)→MySQL(운영, `DATABASE_URL` 전환)
- **최적화**: Google OR-Tools (VRPTW) — 폴백: NN+2-opt
- **지도/데이터**: Leaflet(자체 호스팅) + OSM 타일 · Nominatim(검색/지오코딩) · Overpass(POI) · OSRM(경로) — 전부 무료·API 키 불필요, 서버 프록시 경유(초당 1회 스로틀)
- **AI 추천**: Google Gemini API(`gemini-flash-latest`, 무료 티어) — `GEMINI_API_KEY` 미설정 시 규칙 기반 스코어링으로 자동 폴백
- **Frontend**: Jinja2 + 바닐라 JS, 미니멀 모노크롬 디자인
- **배포/CI**: Docker Compose(web/db/redis) · Gunicorn · GitHub Actions(ruff+pytest)

## 실행 방법

```bash
# 의존성 (최초 1회)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# DB 초기화 (최초 1회) — Alembic 마이그레이션 적용
FLASK_APP=wsgi.py .venv/bin/flask db upgrade
# 이후 스키마 변경 시: flask db migrate -m "설명" → 리뷰 → flask db upgrade

# 개발 서버 → http://127.0.0.1:5002
.venv/bin/python wsgi.py
```

- **테스트 계정**: `test@test.com` / `test1234` (샘플 여행 포함 — 로컬 DB 초기화 시 다시 만들어야 함)
- 환경변수: [.env.example](.env.example) 참고 (`MAP_ADAPTER_ENABLED=false`면 외부 API 없이 근사 계산만으로 동작, `GEMINI_API_KEY` 미설정 시 AI 추천은 규칙 기반으로 동작)

## 테스트

```bash
.venv/bin/pytest              # 단위+통합 90개 (외부 API 미호출)
.venv/bin/pytest -m e2e       # E2E 5종 (TC-501~505, 실서버+Chromium)
.venv/bin/ruff check .        # lint
# 부하: loadtest/locustfile.py 상단 주석 참고
```

**실측 결과 (2026.07)**: 전 스위트 통과. 부하 30명 동시 — 실패 0%, 조회 p95 290ms(목표 500ms), 경로 생성 p95 1.3s(목표 3s). 100명 — 실패 0%이나 조회 p95 1.4s로 목표 초과(확장 경로: 워커 증설 + Celery 큐 분리).

## 프로젝트 구조

```
app/
  engines/        순수 Python 핵심 엔진 (Flask 비의존)
    route_engine.py     경로 파이프라인·Day 배치·부분 재계산
    route_optimizer.py  OR-Tools VRPTW 솔버
    recommender.py      추천 하드필터+스코어링
    planb_engine.py     Plan B 후보 선정
  adapters/       외부 API 어댑터 (OSM: Nominatim/Overpass/OSRM + Haversine 폴백)
  services/       비즈니스 로직·트랜잭션 경계
  controllers/    Flask Blueprint (REST API + 페이지 뷰)
  models/         SQLAlchemy 모델 (10개 테이블)
  templates/ static/   Jinja2 + JS/CSS (Leaflet 자체 호스팅)
tests/            단위·통합 90개 + tests/e2e/ 시나리오 5종
loadtest/         Locust 부하 테스트
```

## 미구현 / 향후 과제

- **외부 연동 대기**: TourAPI(추천 후보 확대), 기상청(우천 자동 감지 — 현재 Plan B는 수동 발동), 카카오 OAuth, SMTP(재설정 메일 — 현재 개발 모드는 로그 출력)
- **자동 감지**: Plan B 우천/휴무 자동 감지, 영업시간 경고(FR-210)
- **AI 추천 마무리 과제**: 추천 결과 Redis 캐시(무료 티어 쿼터 소진 방지), 수락/거절 피드백을 다음 추천 스코어링에 실제로 반영하는 로직(FR-306은 이력 저장까지만 구현)
- **운영 확장**: 자체 OSRM/Nominatim 인스턴스(현재 공개 데모 서버 — 비상업·저트래픽 한정), 캐시의 Redis 공유화(현재 프로세스 내 TTL), Celery 비동기 큐, OWASP ZAP 스캔
- **참고**: OSM POI 데이터는 번화가·관광지에서 풍부하고 주거지역은 얇음 — 국내 상권 커버리지가 필요하면 카카오/구글 Places 어댑터로 교체(구조 준비됨)

## 개발 로그

변경 이력·의사결정 배경은 [개발_로그.md](개발_로그.md)에 정리한다.
