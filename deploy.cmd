@echo off
REM Deploy script for Azure App Service - Python Flask application

REM 1. Python 가상환경 생성 및 활성화
echo Deploying Python Flask application...
cd /d "%DEPLOYMENT_SOURCE%"

if exist "%DEPLOYMENT_TARGET%\.venv" (
    echo Using existing virtual environment...
) else (
    echo Creating new virtual environment...
    "%PYTHON_EXE%" -m venv "%DEPLOYMENT_TARGET%\.venv"
)

REM 2. 의존성 설치
echo Installing dependencies...
"%DEPLOYMENT_TARGET%\.venv\Scripts\pip.exe" install --upgrade pip
"%DEPLOYMENT_TARGET%\.venv\Scripts\pip.exe" install -r requirements.txt

REM 3. 정적 파일 수집 (필요시)
REM echo Collecting static files...
REM "%DEPLOYMENT_TARGET%\.venv\Scripts\python.exe" manage.py collectstatic --noinput

REM 4. 데이터베이스 마이그레이션 (필요시)
REM echo Running database migrations...
REM "%DEPLOYMENT_TARGET%\.venv\Scripts\python.exe" manage.py migrate

echo Deployment completed successfully!
exit /b 0
