# run.py - 앱 실행 진입점 파일
from app import create_app

# create_app() 팩토리 함수를 호출하여 Flask 앱 인스턴스 생성
app = create_app()

if __name__ == "__main__":
    # 개발 서버 실행 (디버그 모드 활성화)
    print("🚀 VIBE FASHION 쇼핑몰 서버가 시작됩니다! ()")
    app.run(host="127.0.0.1", port=5000, debug=True)
