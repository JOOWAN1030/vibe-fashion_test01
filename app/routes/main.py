import os
import sys
import traceback
from flask import Blueprint, render_template
from dotenv import load_dotenv
from supabase import create_client, Client

# .env 환경 변수 로드
load_dotenv()

# 메인 기능용 Blueprint 객체 생성
main_bp = Blueprint("main", __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase Init Error] {e}", file=sys.stderr)
        traceback.print_exc()

@main_bp.route("/")
def index():
    """
    메인 쇼핑몰 홈 화면
    - Supabase products 테이블에서 is_active=true이고 is_featured=true인 상품 최대 4개 조회
      (is_featured 컬럼이 테이블에 없을 경우 is_active=true 기준으로 조회하도록 fallback 처리)
    - 가격 포맷팅 및 에러 핸들링
    """
    products = []

    try:
        if supabase:
            raw_products = []
            # 1. 요구사항인 is_active=true, is_featured=true 조건 시도
            try:
                response = (
                    supabase.table("products")
                    .select("*, product_images(image_url, is_primary)")
                    .eq("is_active", True)
                    .eq("is_featured", True)
                    .limit(4)
                    .execute()
                )
                raw_products = response.data or []
            except Exception as query_err:
                # is_featured 컬럼이 없을 경우 대비 fallback
                print(f"[Supabase Notice] is_featured 조건 조회 실패 ({query_err}), is_active 기준으로 조회합니다.", file=sys.stderr)
                response = (
                    supabase.table("products")
                    .select("*, product_images(image_url, is_primary)")
                    .eq("is_active", True)
                    .limit(4)
                    .execute()
                )
                raw_products = response.data or []

            for item in raw_products:
                price_val = item.get("sale_price") or item.get("price") or 0
                try:
                    price_int = int(float(price_val))
                    formatted_price = f"{price_int:,}원"
                except (ValueError, TypeError):
                    formatted_price = f"{price_val}원"

                # 썸네일 이미지 추출 (직접 필드 또는 product_images 관계 데이터)
                thumbnail_url = item.get("thumbnail_url") or item.get("image_url")
                if not thumbnail_url and item.get("product_images"):
                    images = item["product_images"]
                    primary_img = next((img["image_url"] for img in images if img.get("is_primary")), None)
                    thumbnail_url = primary_img or (images[0]["image_url"] if images else None)

                if not thumbnail_url:
                    thumbnail_url = "https://picsum.photos/seed/fashion/600/600"

                products.append({
                    "id": item.get("id"),
                    "name": item.get("name", "상품명 없음"),
                    "price": formatted_price,
                    "thumbnail_url": thumbnail_url,
                    "description": item.get("description", ""),
                    "category": item.get("category", "")
                })
        else:
            print("[Supabase Warning] Supabase 클라이언트가 초기화되지 않았습니다.", file=sys.stderr)
    except Exception as e:
        print(f"[Supabase Query Error] 상품 목록 조회 실패: {e}", file=sys.stderr)
        traceback.print_exc()
        products = []

    return render_template("index.html", products=products)

