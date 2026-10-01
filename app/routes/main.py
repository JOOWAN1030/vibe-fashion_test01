# app/routes/main.py - 메인 상품 전시 및 마이페이지 라우트
import sys
import uuid
import traceback
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from app.supabase_client import supabase, get_supabase_admin
from app.routes.auth import login_required, ERROR_MESSAGES, SUCCESS_MESSAGES

main_bp = Blueprint("main", __name__)


def is_valid_uuid(val: str) -> bool:
    """문자열이 유효한 UUID 형식인지 검증"""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


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


@main_bp.route("/products/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지 (GET /products/<product_id>)
    - Supabase에서 product_id로 상품 정보 조회 (카테고리 및 이미지 조인)
    - 상품 이미지, 이름, 가격(할인가/정가), 설명 표시
    - product_options 테이블에서 해당 상품의 색상(color) 목록을 DISTINCT로 조회
    """
    if not supabase:
        flash("데이터베이스 연결을 확인할 수 없습니다.", "danger")
        return redirect(url_for("main.index"))

    try:
        # 1. Supabase에서 product_id로 상품 정보 조회 (UUID 우선, 아닐 경우 slug 조회)
        raw_product = None
        if is_valid_uuid(product_id):
            try:
                resp = (
                    supabase.table("products")
                    .select("*, categories(id, name, slug), product_images(image_url, is_primary, sort_order)")
                    .eq("id", product_id)
                    .maybe_single()
                    .execute()
                )
                raw_product = resp.data if resp else None
            except Exception as query_err:
                print(f"[Supabase Notice] 상품 조인 조회 실패({query_err}), 단일 조회 시도", file=sys.stderr)
                resp = supabase.table("products").select("*").eq("id", product_id).maybe_single().execute()
                raw_product = resp.data if resp else None
        else:
            try:
                resp_slug = (
                    supabase.table("products")
                    .select("*, categories(id, name, slug), product_images(image_url, is_primary, sort_order)")
                    .eq("slug", product_id)
                    .maybe_single()
                    .execute()
                )
                raw_product = resp_slug.data if resp_slug else None
            except Exception:
                raw_product = None

        if not raw_product:
            flash("요청하신 상품을 찾을 수 없습니다.", "warning")
            return redirect(url_for("main.index"))

        real_product_id = raw_product.get("id")

        # 2. 상품 이미지 목록 정리
        images = raw_product.get("product_images") or []
        if not images:
            try:
                img_res = (
                    supabase.table("product_images")
                    .select("image_url, is_primary, sort_order")
                    .eq("product_id", real_product_id)
                    .order("sort_order")
                    .execute()
                )
                images = img_res.data or []
            except Exception:
                images = []

        primary_image = next((img["image_url"] for img in images if img.get("is_primary")), None)
        if not primary_image and images:
            primary_image = images[0]["image_url"]
        if not primary_image:
            primary_image = raw_product.get("thumbnail_url") or "https://images.unsplash.com/photo-1445205170230-053b83016050?w=800&auto=format&fit=crop&q=80"

        # 이미지 URL 리스트
        image_urls = [img["image_url"] for img in images if img.get("image_url")]
        if primary_image not in image_urls:
            image_urls.insert(0, primary_image)
        if not image_urls:
            image_urls = [primary_image]

        # 3. 가격(할인가/정가) 및 할인율 계산
        orig_price = raw_product.get("price") or 0
        sale_price = raw_product.get("sale_price")
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

        # 카테고리 정보
        cat_info = raw_product.get("categories") or {}
        cat_name = cat_info.get("name") if isinstance(cat_info, dict) else "전체"
        cat_slug = cat_info.get("slug") if isinstance(cat_info, dict) else "all"

        slug = raw_product.get("slug", "")
        brand_meta = {
            "basic-crop-tshirt": {"brand": "MLB", "likes": "4.8k", "reviews": 1248, "tag": "무료배송"},
            "wide-denim-pants": {"brand": "8SECONDS", "likes": "3.1k", "reviews": 892, "tag": "오늘출발"},
            "overfit-cotton-jacket": {"brand": "COVERNAT", "likes": "6.2k", "reviews": 2104, "tag": "단독"},
            "floral-midi-dress": {"brand": "VIBE SELECT", "likes": "1.5k", "reviews": 430, "tag": "무료배송"},
            "construction-outer": {"brand": "CARHARTT WIP", "likes": "8.9k", "reviews": 3412, "tag": "쿠폰"},
            "chuck-taylor-all-star-unearthed": {"brand": "CONVERSE", "likes": "12.4k", "reviews": 5920, "tag": "BEST"}
        }.get(slug, {"brand": "VIBE STANDARD", "likes": "1.2k", "reviews": 350, "tag": "무료배송"})

        # 4. product_options 테이블에서 색상(color) 목록 DISTINCT 조회
        colors = []
        seen_colors = set()
        try:
            opt_res = (
                supabase.table("product_options")
                .select("color")
                .eq("product_id", real_product_id)
                .execute()
            )
            for row in (opt_res.data or []):
                color_name = (row.get("color") or "").strip()
                if color_name and color_name not in seen_colors:
                    seen_colors.add(color_name)
                    colors.append(color_name)
        except Exception as opt_err:
            print(f"[Supabase Notice] 옵션 색상 조회 실패: {opt_err}", file=sys.stderr)

        product = {
            "id": real_product_id,
            "name": raw_product.get("name", "상품명 없음"),
            "slug": slug,
            "description": raw_product.get("description", "상세 설명이 등록되지 않은 상품입니다."),
            "brand": brand_meta["brand"],
            "likes": brand_meta["likes"],
            "reviews": brand_meta["reviews"],
            "tag": brand_meta["tag"],
            "price": formatted_price,
            "price_num": numeric_price,
            "original_price": formatted_orig_price if discount_rate else None,
            "discount_rate": discount_rate,
            "primary_image": primary_image,
            "images": image_urls,
            "category_name": cat_name,
            "category_slug": cat_slug
        }

        return render_template("product_detail.html", product=product, colors=colors)

    except Exception as e:
        print(f"[Supabase Query Error] 상품 상세 조회 오류: {e}", file=sys.stderr)
        traceback.print_exc()
        flash("상품 정보를 조회하는 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("main.index"))


@main_bp.route("/api/products/<product_id>/sizes")
def get_product_sizes_api(product_id):
    """
    상품 색상별 사이즈 및 재고 목록 조회 API
    GET /api/products/<product_id>/sizes?color=<선택한 색상>
    - product_options에서 product_id + color로 필터링
    - size, stock을 JSON 배열로 반환
      예: [{"size": "S", "stock": 3}, {"size": "M", "stock": 0}]
    """
    if not supabase:
        return jsonify([]), 500

    color = request.args.get("color", "").strip()
    if not color:
        return jsonify([]), 400

    try:
        real_product_id = product_id
        if not is_valid_uuid(product_id):
            prod_lookup = supabase.table("products").select("id").eq("slug", product_id).maybe_single().execute()
            if prod_lookup and prod_lookup.data:
                real_product_id = prod_lookup.data.get("id")
            else:
                return jsonify([])

        # product_options에서 product_id + color로 필터링 조회
        res = (
            supabase.table("product_options")
            .select("id, size, stock, stock_quantity, additional_price")
            .eq("product_id", real_product_id)
            .eq("color", color)
            .execute()
        )
        raw_options = res.data or []

        sizes_list = []
        for opt in raw_options:
            # stock 컬럼 우선 사용, 없을 경우 stock_quantity 사용
            stock = opt.get("stock")
            if stock is None:
                stock = opt.get("stock_quantity", 0)
            elif stock == 0 and (opt.get("stock_quantity") or 0) > 0:
                stock = opt.get("stock_quantity", 0)

            try:
                stock_int = max(0, int(stock))
            except (ValueError, TypeError):
                stock_int = 0

            sizes_list.append({
                "id": opt.get("id"),
                "size": opt.get("size", "FREE"),
                "stock": stock_int,
                "additional_price": opt.get("additional_price", 0)
            })

        return jsonify(sizes_list)
    except Exception as e:
        print(f"[API Error] /api/products/<product_id>/sizes 조회 실패: {e}", file=sys.stderr)
        return jsonify([]), 500


@main_bp.route("/products/<product_id>/options")
def product_options_api(product_id):
    """
    선택된 색상의 사이즈 목록 및 재고 조회 API (JavaScript fetch 비동기 호출용)
    - color 파라미터로 해당 상품의 옵션 목록 조회
    - color, size, stock(또는 stock_quantity), additional_price 컬럼 사용
    - 재고 0 여부(is_sold_out) 및 남은 수량(stock) 반환
    """
    if not supabase:
        return jsonify({"success": False, "error": "데이터베이스 연결을 확인할 수 없습니다."}), 500

    color = request.args.get("color", "").strip()
    if not color:
        return jsonify({"success": False, "error": "색상(color) 파라미터가 필요합니다."}), 400

    try:
        real_product_id = product_id
        if not is_valid_uuid(product_id):
            prod_lookup = supabase.table("products").select("id").eq("slug", product_id).maybe_single().execute()
            if prod_lookup and prod_lookup.data:
                real_product_id = prod_lookup.data.get("id")
            else:
                return jsonify({"success": True, "product_id": product_id, "color": color, "options": []})

        # Supabase product_options 테이블에서 해당 상품 및 색상 기준 옵션 조회
        res = (
            supabase.table("product_options")
            .select("id, product_id, color, size, stock, stock_quantity, additional_price")
            .eq("product_id", real_product_id)
            .eq("color", color)
            .execute()
        )
        raw_options = res.data or []

        options_list = []
        for opt in raw_options:
            # stock 컬럼 우선 사용, 없을 경우 stock_quantity 사용
            stock = opt.get("stock")
            if stock is None:
                stock = opt.get("stock_quantity", 0)
            elif stock == 0 and (opt.get("stock_quantity") or 0) > 0:
                # 레거시 데이터 호환
                stock = opt.get("stock_quantity", 0)

            try:
                stock_int = max(0, int(stock))
            except (ValueError, TypeError):
                stock_int = 0

            options_list.append({
                "id": opt.get("id"),
                "size": opt.get("size", "FREE"),
                "color": opt.get("color"),
                "stock": stock_int,
                "is_sold_out": (stock_int <= 0),
                "additional_price": opt.get("additional_price", 0)
            })

        return jsonify({
            "success": True,
            "product_id": product_id,
            "color": color,
            "options": options_list
        })
    except Exception as e:
        print(f"[Supabase Notice] 옵션 사이즈 조회 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500


def check_user_has_password_auth(user_id: str | None, session_user: dict, profile_email: str | None = None) -> bool:
    """
    현재 사용자가 일반 이메일/비밀번호 인증 가입자인지 검증
    - 카카오/네이버 등 소셜 전용 계정인 경우 False 반환
    - 세션에 기록된 auth_provider, user.provider를 1차 확인
    - ID 접두어(kakao_, naver_, sns_) 확인
    - Supabase Auth Admin API를 통해 사용자 app_metadata.providers / identities 확인
    """
    if not user_id:
        return False

    str_user_id = str(user_id).lower()
    # 1. 소셜 로그인 식별 접두어 확인 (카카오, 네이버, SNS 테스트 계정)
    if (
        str_user_id.startswith("kakao")
        or str_user_id.startswith("naver")
        or str_user_id.startswith("sns_")
        or "kakao" in str_user_id
    ):
        return False

    # 2. 세션에 명시된 provider / auth_provider 확인
    session_provider = session.get("auth_provider") or session_user.get("provider")
    if session_provider:
        if session_provider.lower() in ("kakao", "naver", "google", "kakaotalk"):
            return False
        if session_provider.lower() == "email":
            return True

    # 3. Supabase Auth 사용자 정보 조회 (UUID 형식인 경우)
    admin = get_supabase_admin()
    if admin:
        try:
            auth_user_resp = admin.auth.admin.get_user_by_id(user_id)
            auth_user = getattr(auth_user_resp, "user", auth_user_resp)
            app_meta = getattr(auth_user, "app_metadata", {}) or {}
            providers = app_meta.get("providers") or []
            main_provider = app_meta.get("provider")

            # 카카오 등 소셜만 있는 경우 제외
            if "email" in providers or main_provider == "email":
                return True

            if getattr(auth_user, "identities", None):
                for ident in auth_user.identities:
                    if getattr(ident, "provider", "") == "email":
                        return True
            return False
        except Exception as e:
            print(f"[Supabase Notice] 사용자 인증 제공자 확인 실패: {e}", file=sys.stderr)

    # 4. 데모 모드 또는 조회 실패 시: 이메일 가입 계정 형태인 경우에만 True
    email = session_user.get("email") or profile_email or ""
    if email and ("kakao" not in email.lower() and "naver" not in email.lower() and "@vibe-fashion.com" not in email):
        return True

    return False


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

    # 이메일/비밀번호 인증 가입자인지 판별 (소셜 전용 가입자는 비밀번호 변경 섹션 숨김)
    has_password_auth = check_user_has_password_auth(user_id, session_user, profile.get("email"))

    return render_template(
        "mypage.html",
        user=profile,
        profile=profile,
        url_msg=url_msg,
        has_password_auth=has_password_auth,
    )


@main_bp.route("/mypage/change-password", methods=["POST"])
@login_required
def change_password():
    """
    비밀번호 변경 처리
    - 소셜(카카오/네이버 등) 로그인 사용자 접근 시 차단
    - 기존 비밀번호 검증 (재로그인 방식으로 확인)
    - 새 비밀번호 유효성 검사 (길이, 일치 여부, 기존 비밀번호와 동일 여부)
    - Supabase update_user_by_id()를 통한 비밀번호 변경
    """
    user_id = session.get("user_id")
    session_user = session.get("user") or {}

    # [백엔드 검증] 소셜 로그인(카카오 등) 사용자의 직접 API 호출 차단
    if not check_user_has_password_auth(user_id, session_user):
        flash("소셜 로그인(카카오 등)으로 가입한 계정은 비밀번호를 변경할 수 없습니다.", "warning")
        return redirect(url_for("main.mypage"))

    email = session_user.get("email")

    # 세션에 이메일이 없는 경우 profiles에서 보완
    if not email and supabase and user_id:
        try:
            res = supabase.table("profiles").select("email").eq("id", user_id).maybe_single().execute()
            if res and res.data:
                email = res.data.get("email")
        except Exception:
            pass

    current_password = request.form.get("current_password", "").strip()
    new_password = request.form.get("new_password", "").strip()
    new_password_confirm = request.form.get("new_password_confirm", "").strip()

    # 필수값 입력 확인
    if not current_password or not new_password or not new_password_confirm:
        flash("모든 비밀번호 항목을 입력해 주세요.", "danger")
        return redirect(url_for("main.mypage"))

    # 새 비밀번호 확인 일치 여부
    if new_password != new_password_confirm:
        flash("새 비밀번호 확인이 일치하지 않습니다.", "danger")
        return redirect(url_for("main.mypage"))

    # 새 비밀번호 길이 규칙 (Day 4 아이디 가입 조건: 최소 6자 이상)
    if len(new_password) < 6:
        flash("새 비밀번호는 최소 6자 이상이어야 합니다.", "danger")
        return redirect(url_for("main.mypage"))

    # 기존 비밀번호와 새 비밀번호 동일 여부 체크
    if current_password == new_password:
        flash("새로운 비밀번호가 현재 비밀번호와 동일합니다.", "danger")
        return redirect(url_for("main.mypage"))

    # 기존 비밀번호 검증 (Supabase 재로그인 시도 방식)
    if not email:
        flash("계정 이메일 정보를 확인할 수 없습니다.", "danger")
        return redirect(url_for("main.mypage"))

    if supabase:
        try:
            auth_test = supabase.auth.sign_in_with_password({
                "email": email,
                "password": current_password,
            })
            if not auth_test or not auth_test.user:
                flash("현재 비밀번호가 일치하지 않습니다.", "danger")
                return redirect(url_for("main.mypage"))
        except Exception:
            flash("현재 비밀번호가 일치하지 않습니다.", "danger")
            return redirect(url_for("main.mypage"))

    # Supabase update_user_by_id()를 사용하여 비밀번호 변경
    admin = get_supabase_admin()
    if not admin:
        flash("인증 관리자 서비스 연결에 실패했습니다.", "danger")
        return redirect(url_for("main.mypage"))

    try:
        admin.auth.admin.update_user_by_id(
            user_id,
            {"password": new_password}
        )
        flash("비밀번호가 변경되었습니다.", "success")
    except Exception as e:
        print(f"[Supabase Error] 비밀번호 업데이트 실패: {e}", file=sys.stderr)
        flash("비밀번호 변경 처리 중 오류가 발생했습니다.", "danger")

    return redirect(url_for("main.mypage"))

