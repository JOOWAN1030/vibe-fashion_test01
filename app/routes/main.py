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
    - Supabase products 테이블에서 활성(status='active') 상품 조회 (카테고리 및 이미지 조인)
    - 할인가, 정상가, 할인율, 카테고리 정보 포맷팅
    """
    products = []
    categories = []

    try:
        if supabase:
            # 1. 카테고리 목록 조회
            try:
                cat_res = supabase.table("categories").select("id, name, slug, sort_order").order("sort_order").execute()
                categories = cat_res.data or []
            except Exception as e:
                print(f"[Supabase Notice] 카테고리 조회 실패: {e}", file=sys.stderr)

            # 2. 상품 목록 조회 (카테고리 정보 및 이미지 조인)
            raw_products = []
            try:
                response = (
                    supabase.table("products")
                    .select("*, categories(id, name, slug), product_images(image_url, is_primary)")
                    .eq("status", "active")
                    .order("created_at", desc=False)
                    .execute()
                )
                raw_products = response.data or []
            except Exception as query_err:
                print(f"[Supabase Notice] 카테고리 조인 조회 실패 ({query_err}), 기본 조회 fallback.", file=sys.stderr)
                try:
                    response = (
                        supabase.table("products")
                        .select("*, product_images(image_url, is_primary)")
                        .eq("status", "active")
                        .execute()
                    )
                    raw_products = response.data or []
                except Exception as e:
                    raw_products = []

            for item in raw_products:
                orig_price = item.get("price") or 0
                sale_price = item.get("sale_price")
                
                # 최종 판매 가격 및 할인율 계산
                try:
                    orig_int = int(float(orig_price))
                    formatted_orig_price = f"{orig_int:,}원"
                except (ValueError, TypeError):
                    orig_int = 0
                    formatted_orig_price = f"{orig_price}원"

                discount_rate = None
                if sale_price is not None:
                    try:
                        sale_int = int(float(sale_price))
                        formatted_price = f"{sale_int:,}원"
                        if orig_int > sale_int and orig_int > 0:
                            discount_rate = int(round((orig_int - sale_int) / orig_int * 100))
                    except (ValueError, TypeError):
                        formatted_price = f"{sale_price}원"
                else:
                    formatted_price = formatted_orig_price

                # 썸네일 이미지 추출
                thumbnail_url = item.get("thumbnail_url") or item.get("image_url")
                if not thumbnail_url and item.get("product_images"):
                    images = item["product_images"]
                    primary_img = next((img["image_url"] for img in images if img.get("is_primary")), None)
                    thumbnail_url = primary_img or (images[0]["image_url"] if images else None)

                if not thumbnail_url:
                    thumbnail_url = "https://images.unsplash.com/photo-1445205170230-053b83016050?w=800&auto=format&fit=crop&q=80"

                # 카테고리 정보 추출
                cat_info = item.get("categories") or {}
                cat_name = cat_info.get("name") if isinstance(cat_info, dict) else item.get("category", "")
                cat_slug = cat_info.get("slug", "all") if isinstance(cat_info, dict) else "all"

                products.append({
                    "id": item.get("id"),
                    "name": item.get("name", "상품명 없음"),
                    "slug": item.get("slug", ""),
                    "price": formatted_price,
                    "original_price": formatted_orig_price if discount_rate else None,
                    "discount_rate": discount_rate,
                    "thumbnail_url": thumbnail_url,
                    "description": item.get("description", ""),
                    "category": cat_name,
                    "category_slug": cat_slug
                })
        else:
            print("[Supabase Warning] Supabase 클라이언트가 초기화되지 않았습니다.", file=sys.stderr)
    except Exception as e:
        print(f"[Supabase Query Error] 상품 목록 조회 실패: {e}", file=sys.stderr)
        traceback.print_exc()
        products = []

    return render_template("index.html", products=products, categories=categories)

