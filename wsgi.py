# wsgi.py - WSGI 진입점 (Azure App Service Linux 호환용)
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
