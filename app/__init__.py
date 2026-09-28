# app/__init__.py - VIBE-FASHION 앱 팩토리 파일
from flask import Flask
from dotenv import load_dotenv
import os

"""
"VIBE FASHION" 패션 쇼핑몰 웹앱
Flask 어플리케이션 팩토리 패턴을 사용하여 앱 인스턴스를 생성하고 설정합니다.
"""

def create_app():
    """
    Flask 애플리케이션 팩토리 함수
    - 환경 변수(.env) 로드
    - 앱 설정 초기화
    - 블루프린트(routes) 등록
    """
    # .env 파일에서 환경 변수를 로드합니다.
    load_dotenv()

    # Flask 앱 인스턴스 생성
    # 템플릿과 정적 파일 폴더 경로를 app 폴더 내로 지정합니다.
    app = Flask(__name__)

    # 기본 환경 설정
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-dev-secret-key")
    app.config["APP_NAME"] = "VIBE FASHION"

    # 라우트(블루프린트) 등록
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    return app
