# app/supabase_client.py - 전역 Supabase 클라이언트 단일 인스턴스 모듈
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase Init Error] {e}", file=sys.stderr)


def get_supabase() -> Client | None:
    """전역 Supabase 클라이언트 반환"""
    global supabase
    if supabase is None and SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        except Exception:
            pass
    return supabase
