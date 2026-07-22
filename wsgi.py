import os

from dotenv import load_dotenv

# .env를 앱 생성 전에 로드해야 config가 GEMINI_API_KEY 등 환경변수를 읽을 수 있다.
# gunicorn(wsgi:app)으로 띄울 때도 모듈 임포트 시점에 로드된다.
load_dotenv()

from app import create_app  # noqa: E402  (load_dotenv 이후에 임포트해야 config가 값을 본다)

app = create_app()

if __name__ == "__main__":
    # 기본 포트 5002 — 5000은 macOS AirPlay 수신기가, 5001은 다른 로컬 프로젝트가 점유
    app.run(port=int(os.environ.get("PORT", 5002)), debug=True)
