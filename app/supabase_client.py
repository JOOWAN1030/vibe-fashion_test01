# app/supabase_client.py - 전역 Supabase 클라이언트 단일 인스턴스 모듈
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# 로컬 개발 환경에서만 .env 파일 로드 (Azure는 Application Settings 사용)
try:
    load_dotenv()
except Exception:
    pass  # .env 파일이 없으면 무시

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase: Client | None = None
supabase_admin: Client | None = None

if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase Init Error] {e}", file=sys.stderr)

if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"[Supabase Admin Init Error] {e}", file=sys.stderr)


def get_supabase() -> Client | None:
    """전역 Supabase 클라이언트 반환"""
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        except Exception:
            pass
    return supabase


def get_supabase_admin() -> Client | None:
    """관리자 권한 Supabase 서비스 롤 클라이언트 반환"""
    global supabase_admin
    if supabase_admin is None and SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception:
            pass
    return supabase_admin
