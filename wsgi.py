import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 기본 포트 5002 — 5000은 macOS AirPlay 수신기가, 5001은 다른 로컬 프로젝트가 점유
    app.run(port=int(os.environ.get("PORT", 5002)), debug=True)
