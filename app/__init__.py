# app/__init__.py - VIBE-FASHION 앱 팩토리 파일
from flask import Flask, jsonify
from dotenv import load_dotenv
import os
import sys
import logging

"""
"VIBE FASHION" 패션 쇼핑몰 웹앱
Flask 어플리케이션 팩토리 패턴을 사용하여 앱 인스턴스를 생성하고 설정합니다.
"""

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def create_app():
    """
    Flask 애플리케이션 팩토리 함수
    - 환경 변수(.env) 로드
    - 앱 설정 초기화
    - 블루프린트(routes) 등록
    """
    logger.info("=" * 60)
    logger.info("🚀 Flask 애플리케이션 시작 중...")
    logger.info("=" * 60)
    
    # .env 파일에서 환경 변수를 로드합니다.
    # Azure 환경에서는 .env 파일이 무시되고 Azure App Service의 Application Settings를 사용합니다.
    # 로컬 개발 환경에서는 .env 파일 사용, 프로덕션에서는 시스템 환경변수 사용
    try:
        load_dotenv()
        logger.info("✓ .env 파일 로드 완료")
    except Exception as e:
        logger.warning(f"⚠ .env 파일 로드 실패: {e}")

    # Flask 앱 인스턴스 생성
    # 템플릿과 정적 파일 폴더 경로를 app 폴더 내로 지정합니다.
    app = Flask(__name__)
    logger.info("✓ Flask 앱 인스턴스 생성 완료")

    # 기본 환경 설정
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-dev-secret-key").strip()
    app.config["APP_NAME"] = "VIBE FASHION"
    app.config["SESSION_COOKIE_NAME"] = "vibe_session"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    logger.info("✓ 기본 설정 완료")

    # Supabase 설정 확인
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    if supabase_url and supabase_key:
        logger.info(f"✓ Supabase 설정 감지: {supabase_url[:50]}...")
    else:
        logger.warning("⚠ Supabase 환경 변수 미설정! (개발 중 또는 테스트 중)")

    # Azure App Service 리버스 프록시 헤더 처리 (HTTPS 인식 보장)
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        logger.info("✓ ProxyFix 미들웨어 등록 완료 (Azure App Service 지원)")
    except Exception as e:
        logger.error(f"❌ ProxyFix 등록 실패: {e}")

    # 라우트(블루프린트) 등록
    try:
        from app.routes.main import main_bp
        from app.routes.auth import auth_bp
        from app.routes.board import board_bp
        from app.routes.order import order_bp, handle_cart_add_logic
        
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(board_bp)
        app.register_blueprint(order_bp)
        logger.info("✓ 모든 Blueprint 등록 완료")
    except Exception as e:
        logger.error(f"❌ Blueprint 등록 실패: {e}")
        raise

    # 요구사항 루트 URL 지원: POST /cart/add
    @app.route("/cart/add", methods=["POST"])
    def root_cart_add():
        return handle_cart_add_logic()

    # 헬스 체크 라우트
    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({
            "status": "healthy",
            "app": "VIBE FASHION",
            "version": "1.0.0"
        }), 200

    # 에러 핸들러
    @app.errorhandler(404)
    def not_found(e):
        logger.warning(f"404 Not Found: {e}")
        return jsonify({"error": "Not Found", "message": str(e)}), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"500 Internal Server Error: {e}")
        return jsonify({"error": "Internal Server Error", "message": str(e)}), 500

    logger.info("=" * 60)
    logger.info("✅ Flask 애플리케이션 시작 완료!")
    logger.info("=" * 60)
    
    return app
    def root_cart_add():
        return handle_cart_add_logic()

    return app
