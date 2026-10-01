# app/routes/order.py - VIBE STORE 장바구니 및 모의 주문/결제 라우트
import sys
import uuid
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.supabase_client import supabase, get_supabase_admin

order_bp = Blueprint("order", __name__, url_prefix="/order")


def get_cart():
    """세션 기반 장바구니 리스트 반환"""
    if "cart" not in session:
        session["cart"] = []
    return session["cart"]


def calculate_cart_totals(cart):
    """장바구니 총 금액, 배송비, 할인금액, 최종결제금액 계산"""
    total_goods_price = 0
    total_discount = 0

    for item in cart:
        total_goods_price += item["price"] * item["quantity"]

    # 3만원 이상 무료 배송 (미만 시 3,000원)
    shipping_fee = 0 if total_goods_price >= 30000 or total_goods_price == 0 else 3000
    
    # 웰컴 쿠폰 15% 할인 적용 여부 (기본 가용)
    discount_amount = 0
    final_amount = total_goods_price + shipping_fee - discount_amount

    return {
        "total_goods_price": total_goods_price,
        "shipping_fee": shipping_fee,
        "discount_amount": discount_amount,
        "final_amount": final_amount,
        "count": sum(item["quantity"] for item in cart)
    }


# ============================================================
# 1. 장바구니 추가 / 삭제 / 수량변경 API
# ============================================================
@order_bp.route("/cart/add", methods=["POST"])
def add_to_cart_api():
    """상품을 장바구니에 추가 (AJAX 또는 폼 전송)"""
    data = request.get_json(silent=True) if request.is_json else request.form or {}
    # product_option_id가 전달된 경우 요구사항 로직 우선 수행
    if data and "product_option_id" in data:
        return handle_cart_add_logic()

    name = data.get("name")
    price_str = str(data.get("price", "0")).replace("원", "").replace(",", "").strip()
    try:
        price = int(float(price_str))
    except (ValueError, TypeError):
        price = 0

    img = data.get("image_url", "https://picsum.photos/seed/item/400/400")
    option = data.get("option", "FREE / 기본")
    qty = int(data.get("quantity", 1))

    cart = get_cart()

    # 동일 상품 및 옵션이 있는지 확인
    found = False
    for item in cart:
        if item["name"] == name and item.get("option") == option:
            item["quantity"] += qty
            found = True
            break

    if not found:
        cart.append({
            "id": f"cart-{uuid.uuid4().hex[:8]}",
            "name": name,
            "price": price,
            "image_url": img,
            "option": option,
            "quantity": qty
        })

    session["cart"] = cart
    session.modified = True

    totals = calculate_cart_totals(cart)

    if request.is_json:
        return jsonify({
            "success": True,
            "message": f"'{name}' 상품이 장바구니에 담겼습니다.",
            "cartCount": totals["count"],
            "cartTotal": totals["final_amount"]
        })
    else:
        flash(f"'{name}' 상품이 장바구니에 담겼습니다.", "success")
        return redirect(url_for("order.cart_view"))


@order_bp.route("/cart")
def cart_view():
    """
    장바구니 페이지 - Supabase DB 기반 조회
    - carts + product_options + products JOIN
    - 품절 상태 확인
    - 배송비 계산 (50,000원 미만 3,000원)
    """
    user_id = session.get("user_id")
    if not user_id:
        flash("로그인이 필요한 서비스입니다.", "warning")
        return redirect(url_for("auth.login", next=url_for("order.cart_view")))
    
    db = get_supabase_admin() or supabase
    if not db:
        flash("데이터베이스 연결 실패", "danger")
        cart_items = []
    else:
        try:
            # carts + product_options + products + product_images JOIN 조회
            cart_res = (
                db.table("carts")
                .select(
                    "id, quantity, "
                    "product_options(id, color, size, stock_quantity, additional_price, "
                    "products(id, name, price, sale_price, product_images(image_url, is_primary)))"
                )
                .eq("user_id", user_id)
                .execute()
            )
            cart_data = cart_res.data if cart_res else []
            
            # 응답 포맷 정리
            cart_items = []
            for item in cart_data:
                try:
                    opt = item.get("product_options") or {}
                    prod = opt.get("products") or {}
                    
                    # 단가 계산 (할인가 우선)
                    unit_price = prod.get("sale_price") or prod.get("price") or 0
                    unit_price = int(float(unit_price))
                    additional_price = int(float(opt.get("additional_price", 0)))
                    item_unit_price = unit_price + additional_price
                    
                    # 소계
                    quantity = item.get("quantity", 1)
                    subtotal = item_unit_price * quantity
                    
                    # 재고 상태
                    stock_quantity = int(opt.get("stock_quantity", 0))
                    is_out_of_stock = stock_quantity == 0
                    
                    # 상품 이미지 처리 (is_primary 우선, 없으면 첫 번째)
                    images = prod.get("product_images") or []
                    primary_image = None
                    if images:
                        # is_primary = true인 이미지 찾기
                        for img in images:
                            if img.get("is_primary"):
                                primary_image = img
                                break
                    image_url = primary_image.get("image_url") if primary_image else (images[0].get("image_url") if images else None)
                    
                    cart_items.append({
                        "id": item.get("id"),
                        "product_option_id": opt.get("id"),
                        "product_id": prod.get("id"),
                        "name": prod.get("name", "상품"),
                        "color": opt.get("color", "-"),
                        "size": opt.get("size", "-"),
                        "quantity": quantity,
                        "unit_price": item_unit_price,
                        "subtotal": subtotal,
                        "stock_quantity": stock_quantity,
                        "is_out_of_stock": is_out_of_stock,
                        "image_url": image_url
                    })
                except Exception as e:
                    print(f"[Cart View] 아이템 처리 실패: {e}", file=sys.stderr)
                    continue
            
            print(f"[Cart View] user_id={user_id}, items={len(cart_items)}", file=sys.stderr)
        except Exception as e:
            print(f"[Cart View] carts 조회 실패: {e}", file=sys.stderr)
            flash("장바구니 조회 실패", "danger")
            cart_items = []
    
    # 합계 계산
    total_goods_price = sum(item["subtotal"] for item in cart_items)
    
    # 배송비 (50,000원 미만이면 3,000원, 이상이면 무료)
    shipping_fee = 0 if total_goods_price >= 50000 or total_goods_price == 0 else 3000
    
    # 품절 여부 확인
    has_out_of_stock = any(item["is_out_of_stock"] for item in cart_items)
    
    totals = {
        "total_goods_price": total_goods_price,
        "shipping_fee": shipping_fee,
        "final_amount": total_goods_price + shipping_fee,
        "count": sum(item["quantity"] for item in cart_items),
        "has_out_of_stock": has_out_of_stock
    }
    
    return render_template("order/cart.html", cart=cart_items, totals=totals)


@order_bp.route("/cart/update", methods=["POST"])
def update_cart_item():
    """장바구니 상품 수량 변경"""
    data = request.get_json() if request.is_json else request.form
    item_id = data.get("item_id")
    action = data.get("action") # "increase", "decrease", "set"
    new_qty = data.get("quantity")

    cart = get_cart()
    for item in cart:
        if item["id"] == item_id:
            if action == "increase":
                item["quantity"] += 1
            elif action == "decrease":
                item["quantity"] = max(1, item["quantity"] - 1)
            elif action == "set" and new_qty:
                item["quantity"] = max(1, int(new_qty))
            break

    session["cart"] = cart
    session.modified = True

    if request.is_json:
        totals = calculate_cart_totals(cart)
        return jsonify({"success": True, "totals": totals})

    return redirect(url_for("order.cart_view"))


@order_bp.route("/cart/remove/<item_id>", methods=["POST", "GET"])
def remove_cart_item(item_id):
    """장바구니 개별 상품 삭제"""
    cart = get_cart()
    session["cart"] = [item for item in cart if item["id"] != item_id]
    session.modified = True
    flash("상품이 장바구니에서 삭제되었습니다.", "info")
    return redirect(url_for("order.cart_view"))


@order_bp.route("/cart/clear", methods=["POST", "GET"])
def clear_cart():
    """장바구니 비우기"""
    session["cart"] = []
    session.modified = True
    flash("장바구니가 비워졌습니다.", "info")
    return redirect(url_for("order.cart_view"))


@order_bp.route("/cart/<cart_id>", methods=["PATCH"])
def update_cart_quantity(cart_id):
    """
    PATCH /cart/<cart_id> - 장바구니 아이템 수량 변경
    - 요청 body: quantity (변경할 새 수량)
    - 본인 소유의 장바구니 아이템인지 확인 (다른 사용자의 cart_id 접근 차단)
    - quantity가 1 미만이면 에러
    - 변경하려는 quantity가 해당 옵션의 stock을 초과하면
      "재고가 부족합니다(현재 N개)" 에러, 변경하지 않음
    - 성공 시 UPDATE 후 새 소계(subtotal) 반환
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
    
    data = request.get_json() or {}
    new_quantity = data.get("quantity")
    
    # quantity 검증
    try:
        new_quantity = int(new_quantity)
        if new_quantity < 1:
            return jsonify({"success": False, "message": "수량은 1개 이상이어야 합니다."}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "유효하지 않은 수량입니다."}), 400
    
    db = get_supabase_admin() or supabase
    if not db:
        return jsonify({"success": False, "message": "데이터베이스 연결 실패"}), 500
    
    # cart 조회 및 본인 소유 확인
    try:
        cart_res = db.table("carts").select("*").eq("id", cart_id).maybe_single().execute()
        cart_item = cart_res.data if cart_res else None
    except Exception as e:
        print(f"[Cart Update] carts 조회 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "장바구니 조회 실패"}), 500
    
    if not cart_item:
        return jsonify({"success": False, "message": "장바구니 아이템을 찾을 수 없습니다."}), 404
    
    if cart_item.get("user_id") != user_id:
        return jsonify({"success": False, "message": "접근 권한이 없습니다."}), 403
    
    # product_option의 stock 및 가격 정보 확인
    product_option_id = cart_item.get("product_option_id")
    try:
        opt_res = db.table("product_options").select("stock_quantity, additional_price, products(price, sale_price)").eq("id", product_option_id).maybe_single().execute()
        option_data = opt_res.data if opt_res else None
    except Exception as e:
        print(f"[Cart Update] product_options 조회 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "상품 옵션 조회 실패"}), 500
    
    if not option_data:
        return jsonify({"success": False, "message": "상품 옵션을 찾을 수 없습니다."}), 404
    
    stock_quantity = int(option_data.get("stock_quantity", 0))
    
    # 재고 확인
    if new_quantity > stock_quantity:
        return jsonify({
            "success": False,
            "message": f"재고가 부족합니다(현재 {stock_quantity}개)"
        }), 400
    
    # cart UPDATE
    try:
        update_payload = {
            "quantity": new_quantity,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        db.table("carts").update(update_payload).eq("id", cart_id).execute()
    except Exception as e:
        print(f"[Cart Update] cart 업데이트 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "수량 업데이트 실패"}), 500
    
    # subtotal 계산
    product_data = option_data.get("products") or {}
    unit_price = product_data.get("sale_price") or product_data.get("price") or 0
    try:
        unit_price = int(float(unit_price))
    except (ValueError, TypeError):
        unit_price = 0
    
    additional_price = int(float(option_data.get("additional_price", 0)))
    item_price = unit_price + additional_price
    subtotal = item_price * new_quantity
    
    return jsonify({
        "success": True,
        "message": "수량이 변경되었습니다.",
        "subtotal": subtotal,
        "quantity": new_quantity,
        "unit_price": item_price
    })


@order_bp.route("/cart/<cart_id>", methods=["DELETE"])
def delete_cart_item(cart_id):
    """
    DELETE /cart/<cart_id> - 장바구니 아이템 삭제
    - 요청: DELETE /order/cart/{product_option_id}
    - 본인 소유의 장바구니 아이템인지 확인 후 삭제
    - 성공 시 JSON 응답
    Note: cart_id 파라미터는 product_option_id로 해석됨 (세션에서만 가용)
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
    
    db = get_supabase_admin() or supabase
    if not db:
        return jsonify({"success": False, "message": "데이터베이스 연결 실패"}), 500
    
    # user_id + product_option_id로 cart 조회 및 소유권 확인
    try:
        cart_res = (
            db.table("carts")
            .select("id")
            .eq("user_id", user_id)
            .eq("product_option_id", cart_id)
            .maybe_single()
            .execute()
        )
        cart_item = cart_res.data if cart_res else None
    except Exception as e:
        print(f"[Cart Delete] carts 조회 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "장바구니 조회 실패"}), 500
    
    if not cart_item:
        return jsonify({"success": False, "message": "장바구니 아이템을 찾을 수 없습니다."}), 404
    
    # cart DELETE (id로 삭제)
    try:
        db.table("carts").delete().eq("id", cart_item["id"]).execute()
        print(f"[Cart Delete] cart 삭제 성공: {cart_item['id']}", file=sys.stderr)
    except Exception as e:
        print(f"[Cart Delete] cart 삭제 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "삭제 실패"}), 500
    
    # 세션 장바구니도 동기화 (product_option_id로 매칭)
    cart = get_cart()
    session["cart"] = [
        item for item in cart 
        if item.get("product_option_id") != cart_id
    ]
    session.modified = True
    
    return jsonify({
        "success": True,
        "message": "상품이 장바구니에서 삭제되었습니다."
    })


# ============================================================
# 2. 주문서 작성 및 모의 결제 (Checkout)
# ============================================================
AVAILABLE_COUPONS = [
    {
        "code": "WELCOME15",
        "name": "[신규회원] 웰컴 15% 전품목 할인 쿠폰",
        "type": "percent",
        "value": 15,
        "badge": "15%"
    },
    {
        "code": "OUTER20",
        "name": "[시즌오프] 아우터/슈즈 페스티벌 20% 특별 쿠폰",
        "type": "percent",
        "value": 20,
        "badge": "20%"
    },
    {
        "code": "VIBE5000",
        "name": "[앱전용] 첫 구매 감사 5,000원 즉시 할인권",
        "type": "amount",
        "value": 5000,
        "badge": "5천원"
    },
    {
        "code": "FREESHIP",
        "name": "[VIP] 전 지역 무조건 무료 배송 티켓",
        "type": "shipping",
        "value": 3000,
        "badge": "배송비"
    }
]


@order_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    """주문서 작성 페이지"""
    cart = get_cart()
    if not cart:
        flash("장바구니에 담긴 상품이 없습니다.", "warning")
        return redirect(url_for("main.index"))

    totals = calculate_cart_totals(cart)
    user = session.get("user", {})

    return render_template(
        "order/checkout.html",
        cart=cart,
        totals=totals,
        user=user,
        coupons=AVAILABLE_COUPONS
    )


@order_bp.route("/pay", methods=["POST"])
def process_payment():
    """모의 결제 승인 처리"""
    cart = get_cart()
    if not cart:
        flash("결제할 상품이 존재하지 않습니다.", "danger")
        return redirect(url_for("main.index"))

    totals = calculate_cart_totals(cart)

    # 폼 입력값 추출
    orderer_name = request.form.get("orderer_name", "").strip() or "주문자"
    orderer_phone = request.form.get("orderer_phone", "").strip() or "010-1234-5678"
    orderer_email = request.form.get("orderer_email", "").strip() or "customer@vibe.com"
    shipping_name = request.form.get("shipping_name", "").strip() or orderer_name
    shipping_phone = request.form.get("shipping_phone", "").strip() or orderer_phone
    shipping_address = request.form.get("shipping_address", "").strip() or "서울특별시 성동구 아차산로 13길 11"
    shipping_memo = request.form.get("shipping_memo", "배송 전 연락 바랍니다.")
    pay_method = request.form.get("pay_method", "card") # "card", "kakaopay", "tosspay", "vbank"
    selected_coupon_code = request.form.get("selected_coupon_code", "").strip()

    # 쿠폰 적용 로직
    discount_val = 0
    coupon_name = None
    applied_coupon = next((c for c in AVAILABLE_COUPONS if c["code"] == selected_coupon_code), None)
    
    if applied_coupon:
        coupon_name = applied_coupon["name"]
        if applied_coupon["type"] == "percent":
            discount_val = int(totals["total_goods_price"] * (applied_coupon["value"] / 100))
        elif applied_coupon["type"] == "amount":
            discount_val = min(totals["total_goods_price"], applied_coupon["value"])
        elif applied_coupon["type"] == "shipping":
            discount_val = totals["shipping_fee"]

    final_pay = max(0, totals["total_goods_price"] + totals["shipping_fee"] - discount_val)

    # 고유 주문번호 생성 (예: 20260928-VB8912)
    order_number = f"{datetime.datetime.now().strftime('%Y%m%d')}-VB{uuid.uuid4().hex[:6].upper()}"

    order_data = {
        "order_number": order_number,
        "ordered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "orderer_name": orderer_name,
        "orderer_phone": orderer_phone,
        "orderer_email": orderer_email,
        "shipping_name": shipping_name,
        "shipping_phone": shipping_phone,
        "shipping_address": shipping_address,
        "shipping_memo": shipping_memo,
        "pay_method": pay_method,
        "coupon_name": coupon_name,
        "total_goods_price": totals["total_goods_price"],
        "shipping_fee": totals["shipping_fee"],
        "discount_amount": discount_val,
        "final_amount": final_pay,
        "order_items": list(cart)
    }

    # Supabase orders 테이블에 기록 시도 (선택적)
    if supabase and session.get("user") and session["user"].get("id") != "demo":
        try:
            supabase.table("orders").insert({
                "user_id": session["user"]["id"],
                "order_number": order_number,
                "total_amount": totals["total_goods_price"],
                "discount_amount": discount_val,
                "final_amount": final_pay,
                "status": "paid",
                "recipient_name": shipping_name,
                "recipient_phone": shipping_phone,
                "shipping_address": shipping_address,
                "memo": shipping_memo
            }).execute()
        except Exception as e:
            print(f"[Supabase Order Save Notice] {e}", file=sys.stderr)

    # 장바구니 비우기 및 결제 완료 세션 저장
    session["cart"] = []
    session["last_order"] = order_data
    session.modified = True

    return redirect(url_for("order.order_complete"))


@order_bp.route("/complete")
def order_complete():
    """모의 결제 완료 화면"""
    last_order = session.get("last_order")
    if not last_order:
        flash("최근 결제 내역이 없습니다.", "info")
        return redirect(url_for("main.index"))

    return render_template("order/complete.html", order=last_order)


# ============================================================
# 3. 요구사항 엔드포인트: POST /cart/add (루트 경로 지원)
# ============================================================
def handle_cart_add_logic():
    """
    POST /cart/add 및 POST /order/cart/add 공통 처리 로직
    - 요청 body: product_option_id, quantity
    - 비로그인 사용자는 /auth/login 으로 리다이렉트
    - product_options.stock 조회해서 요청 수량보다 적으면
      "재고가 부족합니다(현재 N개)" 에러 반환, DB에 아무 것도 쓰지 않음
    - carts 테이블에 upsert (같은 옵션이면 수량 누적)
    - 누적 후 수량이 재고를 초과하게 되는 경우도 동일하게 에러 처리
    - 성공 시 JSON: {"success": true, "message": "장바구니에 담겼습니다"}
    """
    print(f"[Cart Add] 요청 시작", file=sys.stderr)
    
    user_id = session.get("user_id")
    # 비로그인 사용자는 /auth/login 으로 리다이렉트
    if not user_id:
        print(f"[Cart Add] 비로그인 사용자", file=sys.stderr)
        if request.is_json:
            return jsonify({
                "success": False,
                "error": "login_required",
                "message": "로그인이 필요한 서비스입니다.",
                "redirect": url_for("auth.login", next=request.referrer or url_for("main.index"))
            }), 401
        flash("로그인이 필요한 서비스입니다.", "warning")
        return redirect(url_for("auth.login", next=request.url))

    data = request.get_json(silent=True) or request.form or {}
    product_option_id = data.get("product_option_id")
    raw_qty = data.get("quantity", 1)

    print(f"[Cart Add] user_id={user_id}", file=sys.stderr)
    print(f"[Cart Add] product_option_id={product_option_id}", file=sys.stderr)
    print(f"[Cart Add] quantity={raw_qty}", file=sys.stderr)

    try:
        quantity = int(raw_qty)
        if quantity <= 0:
            return jsonify({"success": False, "message": "수량은 1개 이상이어야 합니다."}), 400
    except (ValueError, TypeError) as e:
        print(f"[Cart Add] 수량 변환 실패: {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "유효하지 않은 수량입니다."}), 400

    if not product_option_id:
        print(f"[Cart Add] product_option_id 없음", file=sys.stderr)
        return jsonify({"success": False, "message": "상품 옵션을 선택해 주세요."}), 400

    # 항상 admin 클라이언트 사용 (RLS 우회로 cart insert/upsert 권한 확보)
    db = get_supabase_admin()
    if not db:
        db = supabase
    if not db:
        print(f"[Cart Add] DB 클라이언트 없음", file=sys.stderr)
        return jsonify({"success": False, "message": "데이터베이스 연결을 확인할 수 없습니다."}), 500

    try:
        # 0. 사용자 프로필 확인 및 자동 생성 (카카오/네이버 로그인 후 profiles 미생성 대비)
        print(f"[Cart Add] profiles 확인/생성 로직 시작", file=sys.stderr)
        try:
            profile_check = db.table("profiles").select("id").eq("id", user_id).maybe_single().execute()
            profile_exists = profile_check and profile_check.data if profile_check else False
            
            if not profile_exists:
                print(f"[Cart Add] profiles에 사용자 없음, 자동 생성 시도", file=sys.stderr)
                user_info = session.get("user", {})
                
                # auth.users에 외래키 제약이 있는 경우를 대비해 INSERT 시도
                # 실패하면 무시하고 진행 (카카오/네이버 로그인의 경우 auth.users에 없을 수 있음)
                try:
                    db.table("profiles").insert({
                        "id": user_id,
                        "email": user_info.get("email", f"{user_id[:8]}@vibe.local"),
                        "name": user_info.get("name", "회원")
                    }).execute()
                    print(f"[Cart Add] profiles 자동 생성 성공", file=sys.stderr)
                except Exception as insert_err:
                    # 외래키 제약으로 실패할 수 있음 - 무시하고 진행
                    print(f"[Cart Add] profiles INSERT 실패 (무시): {insert_err}", file=sys.stderr)
        except Exception as profile_check_err:
            print(f"[Cart Add] profiles 확인 실패 (무시하고 진행): {profile_check_err}", file=sys.stderr)
        
        # 1. product_options에서 stock 및 상품 정보 조회
        print(f"[Cart Add] product_options 조회 시작", file=sys.stderr)
        opt_res = (
            db.table("product_options")
            .select("id, product_id, color, size, stock, stock_quantity, additional_price, products(name, price, sale_price)")
            .eq("id", product_option_id)
            .maybe_single()
            .execute()
        )
        option_data = opt_res.data if opt_res else None
        print(f"[Cart Add] product_options 조회 결과: {option_data is not None}", file=sys.stderr)

        if not option_data:
            return jsonify({"success": False, "message": "존재하지 않는 상품 옵션입니다."}), 404

        # 재고 수량 계산 (stock 컬럼 우선, 보조로 stock_quantity 참조)
        current_stock = option_data.get("stock")
        if current_stock is None:
            current_stock = option_data.get("stock_quantity", 0)
        elif current_stock == 0 and (option_data.get("stock_quantity") or 0) > 0:
            current_stock = option_data.get("stock_quantity", 0)

        try:
            current_stock = max(0, int(current_stock))
        except (ValueError, TypeError):
            current_stock = 0

        # 2. 담기 전에 product_options.stock을 조회해서 요청 수량보다 적으면
        #    "재고가 부족합니다(현재 N개)" 에러 반환, DB에 아무 것도 쓰지 않음
        if quantity > current_stock:
            return jsonify({
                "success": False,
                "message": f"재고가 부족합니다(현재 {current_stock}개)"
            }), 400

        # 3. 기존 carts 테이블에 동일 옵션이 있는지 조회
        cart_res = (
            db.table("carts")
            .select("id, quantity")
            .eq("user_id", user_id)
            .eq("product_option_id", product_option_id)
            .maybe_single()
            .execute()
        )
        existing_cart_item = cart_res.data if cart_res else None

        new_total_qty = quantity
        if existing_cart_item:
            existing_qty = int(existing_cart_item.get("quantity") or 0)
            new_total_qty = existing_qty + quantity

            # 4. 누적 수량이 재고를 초과하게 되는 경우도 동일하게 에러 처리
            if new_total_qty > current_stock:
                return jsonify({
                    "success": False,
                    "message": f"재고가 부족합니다(현재 {current_stock}개)"
                }), 400

        # 5. carts 테이블에 upsert
        upsert_payload = {
            "user_id": user_id,
            "product_option_id": product_option_id,
            "quantity": new_total_qty,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        if existing_cart_item and existing_cart_item.get("id"):
            upsert_payload["id"] = existing_cart_item["id"]

        db.table("carts").upsert(upsert_payload, on_conflict="user_id,product_option_id").execute()

        # 6. 세션 장바구니 동기화 (기존 헤더 카운트 및 장바구니 뷰와의 호환성 유지)
        prod_meta = option_data.get("products") or {}
        prod_name = prod_meta.get("name") or data.get("name") or "상품"
        unit_price = prod_meta.get("sale_price") or prod_meta.get("price") or 0
        try:
            unit_price = int(float(unit_price))
        except (ValueError, TypeError):
            unit_price = 0

        add_price = int(float(option_data.get("additional_price") or 0))
        final_item_price = unit_price + add_price
        opt_label = f"{option_data.get('color', '')} / {option_data.get('size', '')}".strip(" /")

        cart = get_cart()
        found_in_session = False
        for item in cart:
            if item.get("product_option_id") == product_option_id or (item.get("name") == prod_name and item.get("option") == opt_label):
                item["quantity"] = new_total_qty
                item["product_option_id"] = product_option_id
                found_in_session = True
                break

        if not found_in_session:
            cart.append({
                "id": f"cart-{uuid.uuid4().hex[:8]}",
                "product_option_id": product_option_id,
                "name": prod_name,
                "price": final_item_price,
                "image_url": data.get("image_url", "https://picsum.photos/seed/item/400/400"),
                "option": opt_label,
                "quantity": new_total_qty
            })

        session["cart"] = cart
        session.modified = True

        totals = calculate_cart_totals(cart)

        return jsonify({
            "success": True,
            "message": "장바구니에 담겼습니다",
            "cartCount": totals["count"]
        })

    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"[Cart Add Error] {error_type}: {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({
            "success": False,
            "message": "장바구니 처리 중 오류가 발생했습니다."
        }), 500
