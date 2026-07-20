"""E2E 전용 픽스처 — 임시 DB로 실서버를 띄우고 Playwright 브라우저로 구동한다.

외부(OSM) 호출은 하지 않는다(MAP_ADAPTER_ENABLED=false): 데모 서버 사용 정책 준수 +
테스트 결정성 확보. 지도 어댑터 실연동은 어댑터 코드 자체와 별도 수동 검증으로 다룬다.
"""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

E2E_PORT = 5057
BASE_URL = f"http://127.0.0.1:{E2E_PORT}"

BOOT_SCRIPT = """
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
app.run(port={port}, debug=False)
""".format(port=E2E_PORT)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{db_path}",
        MAP_ADAPTER_ENABLED="false",
        SECRET_KEY="e2e-secret",
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", BOOT_SCRIPT],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE_URL + "/healthz", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("E2E server failed to start")
        yield BASE_URL
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser, live_server):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page._console_errors = errors
    yield page
    context.close()
    assert errors == [], f"콘솔/페이지 에러 발생: {errors}"
