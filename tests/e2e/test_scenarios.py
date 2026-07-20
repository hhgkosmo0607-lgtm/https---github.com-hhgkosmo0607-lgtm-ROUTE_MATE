"""13.5절 E2E 시나리오 — TC-501~505.

각 테스트는 실제 서버 + 실제 Chromium으로 사용자의 클릭 흐름을 그대로 재현한다.
드래그 앤 드롭은 순서 버튼(▲▼)·Day 선택으로 대체 구현되어 있으므로 그 UI를 검증한다.
"""

import time as clock

import pytest

pytestmark = pytest.mark.e2e

SEOUL = [
    ("경복궁", "ATTRACTION", "37.5796", "126.9770"),
    ("명동", "SHOPPING", "37.5636", "126.9834"),
    ("남산타워", "ATTRACTION", "37.5512", "126.9882"),
    ("이태원", "ETC", "37.5346", "126.9946"),
    ("동대문", "SHOPPING", "37.5714", "127.0095"),
]


def _unique_email(tag):
    return f"{tag}{int(clock.time() * 1000) % 10**9}@e2e.com"


def _signup(page, base, email, nickname="이투이"):
    page.goto(base + "/signup")
    page.fill("#nickname", nickname)
    page.fill("#email", email)
    page.fill("#password", "abcd1234")
    page.click("button[type=submit]")
    page.wait_for_url("**/mypage*")


def _login(page, base, email):
    page.goto(base + "/login")
    page.fill("#email", email)
    page.fill("#password", "abcd1234")
    page.click("button[type=submit]")
    page.wait_for_url("**/trips")


def _logout(page):
    page.click("#logout-btn")
    page.wait_for_url("**/")


def _create_trip(page, base, title="E2E 여행", start="2026-09-01", end="2026-09-03"):
    page.goto(base + "/trips/new")
    page.fill("#title", title)
    page.fill("#region", "서울")
    page.fill("#start_date", start)
    page.fill("#end_date", end)
    page.click("button[type=submit]")
    page.wait_for_url("**/plan")
    return page.url.split("/trips/")[1].split("/")[0]


def _add_places_and_route(page, places=SEOUL):
    page.click("#manual-entry summary")
    for name, cat, lat, lng in places:
        page.fill("#place_name", name)
        page.select_option("#place_category", cat)
        page.fill("#place_lat", lat)
        page.fill("#place_lng", lng)
        page.click("#add-place-form button[type=submit]")
        page.wait_for_selector(f"#unassigned-list >> text={name}")
    page.click("#generate-route-btn")
    page.wait_for_selector("#day-tabs a", timeout=30000)
    page.wait_for_timeout(300)


def test_tc501_first_trip_complete(page, live_server):
    """TC-501: 가입→프로필→여행 생성→장소 5개→경로 생성 → 타임라인·지도 정상 표시."""
    email = _unique_email("tc501")
    _signup(page, live_server, email)

    # 프로필 설정
    page.select_option("#travel_style", "SIGHTSEEING")
    page.select_option("#transport", "CAR")
    page.click("#profile-form button[type=submit]")
    page.wait_for_selector("text=프로필을 저장했습니다.")

    trip_id = _create_trip(page, live_server)
    _add_places_and_route(page)

    # 타임라인: 5개 장소 전부 Day에 배치, 이동시간 배지 존재
    status = page.locator("#route-status").inner_text()
    assert "총 이동" in status
    page.click("#day-tabs a")  # Day 1
    assert page.locator("#day-content [data-schedule-id]").count() >= 1

    # 지도 화면: Leaflet 컨테이너 + Day 요약 렌더링
    page.goto(f"{live_server}/trips/{trip_id}/map")
    page.wait_for_selector("#map .leaflet-container, #map.leaflet-container", timeout=15000)
    page.wait_for_selector("#day-summary table")
    total_rows = page.locator("#day-summary tbody tr").count()
    assert total_rows == len(SEOUL)


def test_tc502_reorder_and_recalc(page, live_server):
    """TC-502: 일정 편집(순서/Day 이동) 시 이동시간 재계산·자동 저장."""
    email = _unique_email("tc502")
    _signup(page, live_server, email)
    _create_trip(page, live_server)
    _add_places_and_route(page)

    # Day 1 첫 항목을 Day 2로 이동
    first_card = page.locator("#day-content [data-schedule-id]").first
    moved_id = first_card.get_attribute("data-schedule-id")
    first_card.locator(".day-move-select").select_option("2")
    page.wait_for_timeout(1000)

    # Day 2 탭에서 이동된 항목 확인 + 새 Day의 첫 항목이면 이동시간 없음
    page.locator('#day-tabs a[data-day="2"]').click()
    page.wait_for_timeout(300)
    moved = page.locator(f'#day-content [data-schedule-id="{moved_id}"]')
    assert moved.count() == 1

    # 새로고침 후에도 유지 (자동 저장 검증)
    page.reload()
    page.wait_for_selector("#day-tabs a")
    page.locator('#day-tabs a[data-day="2"]').click()
    page.wait_for_timeout(300)
    assert page.locator(f'#day-content [data-schedule-id="{moved_id}"]').count() == 1


def test_tc503_recommendation_accept(page, live_server):
    """TC-503: AI 추천 요청 → 수락 → 일정(보관함) 반영."""
    email = _unique_email("tc503")
    _signup(page, live_server, email)
    trip_id = _create_trip(page, live_server)

    # 후보 풀 구성: 장소를 추가했다가 일정에서 제거해 "근처의 미사용 장소"를 만든다
    _add_places_and_route(page, places=SEOUL[:2])  # summary는 이미 열려 있음 (재클릭 시 닫힘)
    page.fill("#place_name", "근처식당")
    page.select_option("#place_category", "RESTAURANT")
    page.fill("#place_lat", "37.5700")
    page.fill("#place_lng", "126.9800")
    page.click("#add-place-form button[type=submit]")
    page.wait_for_selector("#unassigned-list >> text=근처식당")
    page.on("dialog", lambda d: d.accept())  # confirm()은 클릭 전에 핸들러 등록 필요
    page.locator('#unassigned-list [data-schedule-id] button[data-action="delete"]').first.click()
    page.wait_for_selector("#unassigned-list >> text=없음", timeout=10000)

    page.goto(f"{live_server}/trips/{trip_id}/recommend")
    page.select_option("#rec_type", "FOOD")
    page.click("#rec-form button[type=submit]")
    page.wait_for_selector("#rec-results .card", timeout=15000)
    assert "근처식당" in page.locator("#rec-results").inner_text()

    page.locator('#rec-results button[data-action="accept"]').first.click()
    page.wait_for_selector("text=일정(미배치 보관함)에 추가했습니다.")

    page.goto(f"{live_server}/trips/{trip_id}/plan")
    page.wait_for_selector("#unassigned-list >> text=근처식당")


def test_tc504_planb_one_touch(page, live_server):
    """TC-504: Plan B 등록→발동(미리보기)→확정→복원."""
    email = _unique_email("tc504")
    _signup(page, live_server, email)
    trip_id = _create_trip(page, live_server)
    _add_places_and_route(page, places=SEOUL[:3])

    page.goto(f"{live_server}/trips/{trip_id}/planb")
    # <option>은 네이티브 셀렉트 내부라 visible 상태가 되지 않으므로 attached로 대기
    page.wait_for_selector("#schedule-select option", state="attached")
    page.fill("#alt_name", "우천대체카페")
    page.select_option("#alt_category", "CAFE")
    page.fill("#alt_lat", "37.5750")
    page.fill("#alt_lng", "126.9790")
    page.click("#planb-form button[type=submit]")
    page.wait_for_selector("#planb-list >> text=우천대체카페")

    page.locator('#planb-list button[data-action="activate"]').first.click()
    page.wait_for_selector("text=재구성 미리보기")
    page.click("#confirm-btn")
    page.wait_for_selector("text=일정을 재구성했습니다.", timeout=15000)

    # 되돌리기 배너 → 원복
    page.wait_for_selector("#revert-btn", timeout=10000)
    page.click("#revert-btn")
    page.wait_for_selector("text=원래 일정으로 되돌렸습니다.")


def test_tc505_share_and_member(page, live_server):
    """TC-505: 동반자 초대(EDITOR 편집 가능) + 읽기 전용 공유 링크."""
    owner = _unique_email("tc505o")
    member = _unique_email("tc505m")

    # 멤버 계정 먼저 생성
    _signup(page, live_server, member, nickname="동반자")
    _logout(page)

    # 오너: 여행 생성 + 멤버 초대(EDITOR) + 공유 링크 생성
    _signup(page, live_server, owner, nickname="오너")
    trip_id = _create_trip(page, live_server, title="공유 여행")
    _add_places_and_route(page, places=SEOUL[:2])

    share_token = page.evaluate(
        f"api.post('/api/trips/{trip_id}/share/link').then(d => d.share_token)"
    )
    page.evaluate(
        f"api.post('/api/trips/{trip_id}/members', {{email: '{member}', role: 'EDITOR'}})"
    )
    _logout(page)

    # 멤버: 목록에 공유 여행 표시 + 편집 가능(제목 수정)
    _login(page, live_server, member)
    page.wait_for_selector("text=공유 여행")
    result = page.evaluate(
        f"api.put('/api/trips/{trip_id}', {{title: '공유 여행(수정)'}}).then(d => d.title)"
    )
    assert result == "공유 여행(수정)"
    _logout(page)

    # 비로그인 공유 링크: 읽기 전용 페이지 렌더링
    page.goto(f"{live_server}/shared/{share_token}")
    page.wait_for_selector("text=읽기 전용 공유 보기")
    assert "공유 여행(수정)" in page.locator("h1").inner_text()
