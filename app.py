# app.py - Azure App Service Oryx 기본 감지용 진입점
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
