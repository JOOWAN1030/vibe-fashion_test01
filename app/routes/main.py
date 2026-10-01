# app/routes/main.py - 메인 상품 전시 및 마이페이지 라우트
import sys
import traceback
from flask import Blueprint, render_template, session, request
from app.supabase_client import supabase
from app.routes.auth import login_required

main_bp = Blueprint("main", __name__)


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
                        numeric_price = sale_int
                        if orig_int > sale_int and orig_int > 0:
                            discount_rate = int(round((orig_int - sale_int) / orig_int * 100))
                    except (ValueError, TypeError):
                        formatted_price = f"{sale_price}원"
                        numeric_price = orig_int
                else:
                    formatted_price = formatted_orig_price
                    numeric_price = orig_int

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

                # 무신사 스타일 브랜드 및 메타데이터 매핑
                slug = item.get("slug", "")
                brand_meta = {
                    "basic-crop-tshirt": {"brand": "MLB", "likes": "4.8k", "reviews": 1248, "tag": "무료배송"},
                    "wide-denim-pants": {"brand": "8SECONDS", "likes": "3.1k", "reviews": 892, "tag": "오늘출발"},
                    "overfit-cotton-jacket": {"brand": "COVERNAT", "likes": "6.2k", "reviews": 2104, "tag": "단독"},
                    "floral-midi-dress": {"brand": "VIBE SELECT", "likes": "1.5k", "reviews": 430, "tag": "무료배송"},
                    "construction-outer": {"brand": "CARHARTT WIP", "likes": "8.9k", "reviews": 3412, "tag": "쿠폰"},
                    "chuck-taylor-all-star-unearthed": {"brand": "CONVERSE", "likes": "12.4k", "reviews": 5920, "tag": "BEST"}
                }.get(slug, {"brand": "VIBE STANDARD", "likes": "1.2k", "reviews": 350, "tag": "무료배송"})

                products.append({
                    "id": item.get("id"),
                    "name": item.get("name", "상품명 없음"),
                    "slug": slug,
                    "brand": brand_meta["brand"],
                    "likes": brand_meta["likes"],
                    "reviews": brand_meta["reviews"],
                    "tag": brand_meta["tag"],
                    "price": formatted_price,
                    "price_num": numeric_price,
                    "created_at": item.get("created_at") or "",
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


@main_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """
    회원 마이페이지
    - login_required 검사 (미인증 시 /auth/login 으로 이동)
    - profiles 테이블에서 로그인 사용자 정보(name, email, address, phone 등) 조회
    - POST 요청 시 기본 배송지 및 회원 정보 수정 지원
    """
    user_id = session.get("user_id")
    session_user = session.get("user") or {}
    msg = request.args.get("msg")
    url_msg = "이메일 인증이 성공적으로 완료되었습니다!" if msg == "email_confirmed" else None

    profile = {
        "id": user_id,
        "email": session_user.get("email", ""),
        "name": session_user.get("name", "회원"),
        "phone": "",
        "address": "",
        "grade": "BRONZE",
    }

    # Supabase profiles 테이블 조회
    if supabase and user_id:
        try:
            res = supabase.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
            if res and res.data:
                profile.update(res.data)
            elif not res or not res.data:
                # 프로필 레코드가 없을 경우 세션 정보 바탕으로 초기 생성 시도
                try:
                    init_data = {
                        "id": user_id,
                        "email": session_user.get("email", ""),
                        "name": session_user.get("name", "회원"),
                    }
                    supabase.table("profiles").insert(init_data).execute()
                    profile.update(init_data)
                except Exception:
                    pass
        except Exception as e:
            print(f"[Supabase Notice] 프로필 조회 실패: {e}", file=sys.stderr)

    # 정보 수정 폼 제출 (POST) 처리
    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        new_phone = request.form.get("phone", "").strip()
        new_address = request.form.get("address", "").strip()

        update_payload = {
            "name": new_name or profile["name"],
            "phone": new_phone,
            "address": new_address,
        }

        if supabase and user_id:
            try:
                supabase.table("profiles").update(update_payload).eq("id", user_id).execute()
                profile.update(update_payload)
                # 세션 내 user 객체 정보도 갱신
                if "user" in session and isinstance(session["user"], dict):
                    session["user"]["name"] = profile["name"]
                    session.modified = True
                url_msg = "회원 정보가 성공적으로 수정되었습니다."
            except Exception as e:
                print(f"[Supabase Error] 프로필 수정 실패: {e}", file=sys.stderr)

    return render_template("mypage.html", user=profile, profile=profile, url_msg=url_msg)

