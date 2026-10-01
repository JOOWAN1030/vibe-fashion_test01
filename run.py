# run.py - 앱 실행 진입점 파일
from app import create_app

# create_app() 팩토리 함수를 호출하여 Flask 앱 인스턴스 생성
app = create_app()

if __name__ == "__main__":
    # 개발 서버 실행
    # Azure 배포 시: Gunicorn이 WSGI 서버로 실행 (startup.txt 참고)
    # 로컬 개발 시: Flask 개발 서버로 실행
    print("🚀 VIBE FASHION 쇼핑몰 서버가 시작됩니다!")
    app.run(host="0.0.0.0", port=5000, debug=False)
