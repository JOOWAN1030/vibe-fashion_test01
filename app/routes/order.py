# app/routes/order.py - VIBE STORE 장바구니 및 모의 주문/결제 라우트
import sys
import uuid
import datetime
import re
import random
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from app.supabase_client import supabase, get_supabase_admin
from app.routes.auth import login_required

order_bp = Blueprint("order", __name__, url_prefix="/order")


def get_cart():
    """세션 기반 장바구니 리스트 반환"""
    if "cart" not in session:
        session["cart"] = []
    return session["cart"]


def calculate_cart_totals(cart):
    """장바구니 총 금액, 배송비, 최종결제금액 계산 (5만원 이상 무료배송)"""
    total_goods_price = 0
    for item in cart:
        price = item.get("price") or item.get("unit_price") or 0
        total_goods_price += price * item.get("quantity", 1)

    # 5만원 이상 무료 배송 (미만 시 3,000원)
    shipping_fee = 0 if total_goods_price >= 50000 or total_goods_price == 0 else 3000
    discount_amount = 0
    final_amount = total_goods_price + shipping_fee - discount_amount

    return {
        "total_goods_price": total_goods_price,
        "shipping_fee": shipping_fee,
        "discount_amount": discount_amount,
        "final_amount": final_amount,
        "count": sum(item.get("quantity", 1) for item in cart)
    }


def get_cart_data_for_user(user_id):
    """
    Supabase DB 기반 장바구니 목록 및 집계 조회
    - carts + product_options + products JOIN
    - 단가, 소계, 재고 상태(is_out_of_stock) 계산
    - 배송비 계산 (50,000원 이상 무료, 미만 3,000원)
    """
    db = get_supabase_admin() or supabase
    cart_items = []
    
    if db and user_id:
        try:
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
            for item in cart_data:
                try:
                    opt = item.get("product_options") or {}
                    prod = opt.get("products") or {}
                    
                    unit_price = prod.get("sale_price") or prod.get("price") or 0
                    unit_price = int(float(unit_price))
                    additional_price = int(float(opt.get("additional_price", 0)))
                    item_unit_price = unit_price + additional_price
                    
                    quantity = item.get("quantity", 1)
                    subtotal = item_unit_price * quantity
                    
                    stock_quantity = int(opt.get("stock_quantity", 0))
                    is_out_of_stock = (stock_quantity == 0)
                    
                    images = prod.get("product_images") or []
                    primary_image = None
                    if images:
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
                    print(f"[Cart Data] 아이템 변환 에러: {e}", file=sys.stderr)
                    continue
        except Exception as e:
            print(f"[Cart Data] DB 조회 실패: {e}", file=sys.stderr)

    # fallback for session cart if DB has no items but session has items
    if not cart_items and "cart" in session and session["cart"]:
        for item in session["cart"]:
            price = item.get("price", 0)
            qty = item.get("quantity", 1)
            stock = item.get("stock_quantity", 99)
            cart_items.append({
                "id": item.get("id"),
                "product_option_id": item.get("product_option_id"),
                "product_id": item.get("product_id"),
                "name": item.get("name", "상품"),
                "color": item.get("color", "-"),
                "size": item.get("size", "-"),
                "option": item.get("option", ""),
                "quantity": qty,
                "unit_price": price,
                "subtotal": price * qty,
                "stock_quantity": stock,
                "is_out_of_stock": stock <= 0 or item.get("is_out_of_stock", False),
                "image_url": item.get("image_url")
            })

    total_goods_price = sum(item["subtotal"] for item in cart_items)
    shipping_fee = 0 if total_goods_price >= 50000 or total_goods_price == 0 else 3000
    has_out_of_stock = any(item.get("is_out_of_stock") or item.get("stock_quantity", 0) <= 0 for item in cart_items)
    
    totals = {
        "total_goods_price": total_goods_price,
        "shipping_fee": shipping_fee,
        "final_amount": total_goods_price + shipping_fee,
        "count": sum(item["quantity"] for item in cart_items),
        "has_out_of_stock": has_out_of_stock
    }
    return cart_items, totals


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
    
    cart_items, totals = get_cart_data_for_user(user_id)
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
    """
    주문서 작성 페이지 (GET /order/checkout) 및 결제 처리 (POST /order/checkout)
    - 로그인 필수 (미로그인 시 /auth/login 으로 리다이렉트)
    - 장바구니 비어있으면 /cart 리다이렉트
    - 장바구니에 품절(stock=0) 아이템이 하나라도 있으면 /cart로 리다이렉트하고
      '품절된 상품이 있어 주문할 수 없습니다' 안내
    - 장바구니 아이템 목록 표시 (수정 불가)
    - 배송지 입력 폼: 수령인 이름, 휴대폰 번호, 배송 주소, 메모(선택)
    - 각 필드 최소 형식 검증: 휴대폰 번호 010-0000-0000 패턴, 주소 최소 5자 이상
    - '마이페이지에 저장된 기본 배송지 불러오기' 버튼 (profiles 테이블 조회)
    - 결제 금액 요약 (상품금액 + 배송비 = 최종금액)
    - '결제하기' 버튼 (더미 결제 → 바로 주문 완료 처리)
    """
    user_id = session.get("user_id")
    if not user_id:
        flash("로그인이 필요한 서비스입니다.", "warning")
        return redirect(url_for("auth.login", next=request.url))

    cart_items, totals = get_cart_data_for_user(user_id)

    # 1. 장바구니 비어있으면 /cart 리다이렉트
    if not cart_items:
        flash("장바구니가 비어 있습니다.", "warning")
        return redirect(url_for("order.cart_view"))

    # 2. 장바구니에 품절(stock=0) 아이템이 하나라도 있으면 /cart로 리다이렉트
    if totals["has_out_of_stock"]:
        flash("품절된 상품이 있어 주문할 수 없습니다", "warning")
        return redirect(url_for("order.cart_view"))

    # POST 결제 처리
    if request.method == "POST":
        return create_order()

    # GET: 마이페이지에 저장된 profiles 테이블에서 사용자 기본 정보 조회
    db = get_supabase_admin() or supabase
    profile = {}
    if db and user_id:
        try:
            p_res = db.table("profiles").select("name, phone, address").eq("id", user_id).maybe_single().execute()
            if p_res and p_res.data:
                profile = p_res.data
        except Exception as e:
            print(f"[Checkout Profile Error] {e}", file=sys.stderr)

    return render_template(
        "order/checkout.html",
        cart=cart_items,
        totals=totals,
        profile=profile,
        user=session.get("user", {}),
        coupons=AVAILABLE_COUPONS
    )


@order_bp.route("/api/default-address", methods=["GET"])
def get_default_address():
    """
    마이페이지에 저장된 기본 배송지 불러오기 API
    - profiles 테이블 조회 (name, phone, address)
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = get_supabase_admin() or supabase
    if not db:
        return jsonify({"success": False, "message": "데이터베이스 연결 실패"}), 500

    try:
        p_res = db.table("profiles").select("name, phone, address").eq("id", user_id).maybe_single().execute()
        if p_res and p_res.data:
            data = p_res.data
            has_data = bool(data.get("name") or data.get("phone") or data.get("address"))
            return jsonify({
                "success": True,
                "has_data": has_data,
                "name": data.get("name") or "",
                "phone": data.get("phone") or "",
                "address": data.get("address") or ""
            })
        return jsonify({"success": False, "message": "마이페이지에 등록된 배송지 정보가 없습니다."})
    except Exception as e:
        print(f"[Default Address Error] {e}", file=sys.stderr)
        return jsonify({"success": False, "message": "배송지 정보를 불러오지 못했습니다."}), 500


@order_bp.route("/create", methods=["POST"])
def create_order():
    """
    주문 생성 API (POST /order/create)
    처리 순서:
    1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단, 아무 것도 쓰지 않음)
    2. 배송지 입력값 서버 측 재검증 (휴대폰 번호 패턴, 주소 최소 길이)
    3. 주문번호 생성: 'VF-' + 오늘날짜(YYYYMMDD) + '-' + 4자리 랜덤숫자
       + 밀리초 타임스탬프 뒷 3자리를 덧붙여 충돌 가능성을 낮춤
    4. orders 테이블에 INSERT (status='paid', paid_at=now())
    5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
    6. product_options.stock 차감 - 반드시 조건부 UPDATE 사용:
       UPDATE ... SET stock = stock - 수량 WHERE id = 옵션ID AND stock >= 수량
       영향받은 행이 0개면 "방금 재고가 소진되었습니다" 에러로 롤백 처리
    7. carts 아이템 DELETE
    8. /order/complete/<order_id> 리다이렉트
    기술: service_role 키로 재고 차감 (RLS 우회 필요)
    """
    user_id = session.get("user_id")
    if not user_id:
        if request.is_json:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
        flash("로그인이 필요한 서비스입니다.", "warning")
        return redirect(url_for("auth.login", next=url_for("order.checkout")))

    db = get_supabase_admin()
    if not db:
        db = supabase
    if not db:
        if request.is_json:
            return jsonify({"success": False, "message": "데이터베이스 연결 실패"}), 500
        flash("데이터베이스 연결에 실패했습니다.", "danger")
        return redirect(url_for("order.checkout"))

    # ========================================================
    # 1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단, 아무 것도 쓰지 않음)
    # ========================================================
    cart_items, totals = get_cart_data_for_user(user_id)
    if not cart_items:
        if request.is_json:
            return jsonify({"success": False, "message": "장바구니가 비어 있습니다."}), 400
        flash("장바구니가 비어 있습니다.", "warning")
        return redirect(url_for("order.cart_view"))

    for item in cart_items:
        opt_id = item.get("product_option_id")
        req_qty = item.get("quantity", 1)
        if not opt_id:
            continue
        try:
            opt_res = db.table("product_options").select("id, stock, stock_quantity").eq("id", opt_id).maybe_single().execute()
            opt_data = opt_res.data if opt_res else None
            if not opt_data:
                msg = f"'{item.get('name')}' 상품 옵션을 찾을 수 없습니다."
                if request.is_json:
                    return jsonify({"success": False, "message": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("order.cart_view"))

            cur_stock = opt_data.get("stock")
            if cur_stock is None:
                cur_stock = opt_data.get("stock_quantity", 0)
            elif cur_stock == 0 and (opt_data.get("stock_quantity") or 0) > 0:
                cur_stock = opt_data.get("stock_quantity", 0)

            cur_stock = int(cur_stock)
            if cur_stock < req_qty or cur_stock <= 0:
                msg = f"'{item.get('name')}' 상품의 재고가 부족합니다. (현재 재고: {cur_stock}개, 요청: {req_qty}개)"
                if request.is_json:
                    return jsonify({"success": False, "message": msg}), 400
                flash(msg, "danger")
                return redirect(url_for("order.cart_view"))
        except Exception as e:
            print(f"[Create Order Stock Check Error] {e}", file=sys.stderr)
            if request.is_json:
                return jsonify({"success": False, "message": "재고 확인 중 오류가 발생했습니다."}), 500
            flash("재고 확인 중 오류가 발생했습니다.", "danger")
            return redirect(url_for("order.cart_view"))

    # ========================================================
    # 2. 배송지 입력값 서버 측 재검증 (휴대폰 번호 패턴, 주소 최소 길이)
    # ========================================================
    req_data = request.get_json(silent=True) if request.is_json else request.form or {}
    recipient_name = (req_data.get("recipient_name") or req_data.get("shipping_name") or "").strip()
    recipient_phone = (req_data.get("recipient_phone") or req_data.get("shipping_phone") or "").strip()
    shipping_address = (req_data.get("shipping_address") or "").strip()
    shipping_memo = (req_data.get("shipping_memo") or req_data.get("memo") or "").strip()
    pay_method = req_data.get("pay_method", "card")

    if not recipient_name:
        if request.is_json:
            return jsonify({"success": False, "message": "수령인 이름을 입력해주세요."}), 400
        flash("수령인 이름을 입력해주세요.", "danger")
        return redirect(url_for("order.checkout"))

    # 휴대폰 번호 패턴 재검증: 010-0000-0000
    if not re.match(r"^010-\d{4}-\d{4}$", recipient_phone):
        if request.is_json:
            return jsonify({"success": False, "message": "휴대폰 번호는 010-0000-0000 형식으로 입력해주세요."}), 400
        flash("휴대폰 번호는 010-0000-0000 형식으로 입력해주세요.", "danger")
        return redirect(url_for("order.checkout"))

    # 주소 최소 길이 재검증: 최소 5자 이상
    if len(shipping_address) < 5:
        if request.is_json:
            return jsonify({"success": False, "message": "배송 주소는 최소 5자 이상 입력해주세요."}), 400
        flash("배송 주소는 최소 5자 이상 입력해주세요.", "danger")
        return redirect(url_for("order.checkout"))

    # 쿠폰 할인 계산
    selected_coupon_code = req_data.get("selected_coupon_code", "").strip()
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

    # ========================================================
    # 3. 주문번호 생성: 'VF-' + 오늘날짜(YYYYMMDD) + '-' + 4자리 랜덤숫자
    #    + 밀리초 타임스탬프 뒷 3자리를 덧붙여 충돌 가능성을 낮춤
    # ========================================================
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    random_4digits = f"{random.randint(0, 9999):04d}"
    ms_3digits = f"{int(time.time() * 1000) % 1000:03d}"
    order_number = f"VF-{today_str}-{random_4digits}{ms_3digits}"
    order_id = str(uuid.uuid4())
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # ========================================================
    # 4. orders 테이블에 INSERT (status='paid', paid_at=now())
    # ========================================================
    order_payload = {
        "id": order_id,
        "user_id": user_id,
        "order_number": order_number,
        "total_amount": totals["total_goods_price"],
        "discount_amount": discount_val,
        "final_amount": final_pay,
        "status": "paid",
        "recipient_name": recipient_name,
        "recipient_phone": recipient_phone,
        "shipping_address": shipping_address,
        "memo": shipping_memo or "요청사항 없음",
        "paid_at": now_iso
    }

    try:
        try:
            db.table("orders").insert(order_payload).execute()
        except Exception as insert_e:
            if "paid_at" in str(insert_e):
                order_payload.pop("paid_at", None)
                db.table("orders").insert(order_payload).execute()
            else:
                raise insert_e
    except Exception as e:
        print(f"[Create Order Insert Orders Error] {e}", file=sys.stderr)
        if request.is_json:
            return jsonify({"success": False, "message": "주문 생성 중 오류가 발생했습니다."}), 500
        flash("주문 생성 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("order.checkout"))

    # ========================================================
    # 5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
    # ========================================================
    order_items_to_insert = []
    for item in cart_items:
        order_items_to_insert.append({
            "order_id": order_id,
            "product_id": item.get("product_id"),
            "product_option_id": item.get("product_option_id"),
            "product_name": item.get("name", "상품"),
            "option_description": f"{item.get('color', '-')}/{item.get('size', '-')}",
            "unit_price": item.get("unit_price", 0),
            "quantity": item.get("quantity", 1),
            "total_price": item.get("subtotal", 0)
        })

    try:
        for oi in order_items_to_insert:
            db.table("order_items").insert(oi).execute()
    except Exception as e:
        print(f"[Create Order Items Insert Error] {e}", file=sys.stderr)
        # 롤백 처리: 생성된 orders 레코드 삭제
        try:
            db.table("order_items").delete().eq("order_id", order_id).execute()
            db.table("orders").delete().eq("id", order_id).execute()
        except Exception as rb_err:
            print(f"[Rollback Orders Error] {rb_err}", file=sys.stderr)
        if request.is_json:
            return jsonify({"success": False, "message": "주문 품목 생성 중 오류가 발생했습니다."}), 500
        flash("주문 품목 처리 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("order.checkout"))

    # ========================================================
    # 6. product_options.stock 차감 - 반드시 조건부 UPDATE 사용:
    #    UPDATE ... SET stock = stock - 수량 WHERE id = 옵션ID AND stock >= 수량
    #    영향받은 행이 0개면 "방금 재고가 소진되었습니다" 에러로 롤백 처리
    #    기술: service_role 키로 재고 차감 (RLS 우회 필요)
    # ========================================================
    decremented_options = []  # list of (opt_id, qty)
    stock_failed = False
    stock_error_msg = ""

    for item in cart_items:
        opt_id = item.get("product_option_id")
        qty = item.get("quantity", 1)
        if not opt_id:
            continue

        try:
            # 현재 재고 조회
            opt_res = db.table("product_options").select("stock, stock_quantity").eq("id", opt_id).maybe_single().execute()
            cur_opt = opt_res.data if opt_res else None
            if not cur_opt:
                stock_failed = True
                stock_error_msg = "방금 재고가 소진되었습니다"
                break

            cur_stock = cur_opt.get("stock")
            if cur_stock is None:
                cur_stock = cur_opt.get("stock_quantity", 0)
            elif cur_stock == 0 and (cur_opt.get("stock_quantity") or 0) > 0:
                cur_stock = cur_opt.get("stock_quantity", 0)

            cur_stock = int(cur_stock)
            new_stock = cur_stock - qty
            if new_stock < 0:
                stock_failed = True
                stock_error_msg = "방금 재고가 소진되었습니다"
                break

            # 조건부 UPDATE: WHERE id = 옵션ID AND stock >= 수량
            update_res = (
                db.table("product_options")
                .update({
                    "stock": new_stock,
                    "stock_quantity": new_stock
                })
                .eq("id", opt_id)
                .gte("stock", qty)
                .execute()
            )

            # 영향받은 행이 0개면 에러로 롤백 처리
            if not update_res.data or len(update_res.data) == 0:
                stock_failed = True
                stock_error_msg = "방금 재고가 소진되었습니다"
                break

            decremented_options.append((opt_id, qty))

        except Exception as e:
            print(f"[Stock Decrement Error] {e}", file=sys.stderr)
            stock_failed = True
            stock_error_msg = "방금 재고가 소진되었습니다"
            break

    # 재고 부족 시 롤백 처리
    if stock_failed:
        print(f"[Create Order] 재고 차감 실패로 롤백 진행: {stock_error_msg}", file=sys.stderr)
        # 1. 이미 차감된 이전 옵션 재고 복원
        for r_opt_id, r_qty in decremented_options:
            try:
                r_res = db.table("product_options").select("stock, stock_quantity").eq("id", r_opt_id).maybe_single().execute()
                if r_res and r_res.data:
                    c_s = r_res.data.get("stock")
                    if c_s is None:
                        c_s = r_res.data.get("stock_quantity", 0)
                    restored = int(c_s) + r_qty
                    db.table("product_options").update({
                        "stock": restored,
                        "stock_quantity": restored
                    }).eq("id", r_opt_id).execute()
            except Exception as r_err:
                print(f"[Rollback Stock Error] {r_err}", file=sys.stderr)

        # 2. order_items 및 orders 삭제
        try:
            db.table("order_items").delete().eq("order_id", order_id).execute()
        except Exception as r_del_err:
            print(f"[Rollback Delete Order Items Error] {r_del_err}", file=sys.stderr)

        try:
            db.table("orders").delete().eq("id", order_id).execute()
        except Exception as r_del_err:
            print(f"[Rollback Delete Order Error] {r_del_err}", file=sys.stderr)

        if request.is_json:
            return jsonify({"success": False, "message": stock_error_msg}), 400
        flash(stock_error_msg, "danger")
        return redirect(url_for("order.cart_view"))

    # ========================================================
    # 7. carts 아이템 DELETE
    # ========================================================
    try:
        db.table("carts").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[Carts Delete Error] {e}", file=sys.stderr)

    # 세션 장바구니 비우기 및 결제 완료 세션 저장
    session["cart"] = []
    session["last_order"] = {
        "order_id": order_id,
        "order_number": order_number,
        "ordered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "shipping_name": recipient_name,
        "shipping_phone": recipient_phone,
        "shipping_address": shipping_address,
        "shipping_memo": shipping_memo or "요청사항 없음",
        "pay_method": pay_method,
        "coupon_name": coupon_name,
        "total_goods_price": totals["total_goods_price"],
        "shipping_fee": totals["shipping_fee"],
        "discount_amount": discount_val,
        "final_amount": final_pay,
        "order_items": [
            {
                "name": item.get("name"),
                "option": f"{item.get('color', '-')}/{item.get('size', '-')}",
                "quantity": item.get("quantity"),
                "price": item.get("unit_price"),
                "image_url": item.get("image_url")
            }
            for item in cart_items
        ]
    }
    session.modified = True

    # ========================================================
    # 8. /order/complete/<order_id> 리다이렉트
    # ========================================================
    flash("주문 및 결제가 성공적으로 완료되었습니다.", "success")
    if request.is_json:
        return jsonify({
            "success": True,
            "order_id": order_id,
            "redirect_url": url_for("order.order_complete_detail", order_id=order_id)
        })
    return redirect(url_for("order.order_complete_detail", order_id=order_id))


@order_bp.route("/pay", methods=["POST"])
def process_payment():
    """모의 결제 승인 처리 (POST /order/pay) - create_order 로 위임"""
    return create_order()


@order_bp.route("/complete/<order_id>")
def order_complete_detail(order_id):
    """
    주문 완료 상세 화면 (GET /order/complete/<order_id>)
    - 로그인 확인 (미인증 시 /auth/login 으로 리다이렉트)
    - 본인 주문이 맞는지 확인 (다른 사용자의 order_id 접근 차단 -> 403 Forbidden)
    - 주문번호, 배송지, 주문 상품 목록, 결제 금액 표시
    - '마이페이지로', '쇼핑 계속하기' 버튼 제공
    """
    user_id = session.get("user_id")
    if not user_id:
        if request.is_json:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
        flash("로그인이 필요한 서비스입니다.", "warning")
        return redirect(url_for("auth.login", error="login_required", next=request.url))

    db = get_supabase_admin() or supabase
    if not db:
        if request.is_json:
            return jsonify({"success": False, "message": "데이터베이스 연결 실패"}), 500
        flash("데이터베이스 연결에 실패했습니다.", "danger")
        return redirect(url_for("main.index"))

    # 1. DB에서 주문 정보 조회 (order_id 기준)
    order_data = None
    try:
        ord_res = db.table("orders").select("*").eq("id", order_id).maybe_single().execute()
        order_data = ord_res.data if ord_res else None
    except Exception as e:
        print(f"[Order Complete View Error] orders 조회 실패: {e}", file=sys.stderr)
        order_data = None

    # 주문이 DB에 없는 경우: 세션 last_order 확인 또는 404
    if not order_data:
        last_order = session.get("last_order")
        if last_order and (last_order.get("order_id") == order_id or not order_id):
            return render_template("order/complete.html", order=last_order)

        if request.is_json:
            return jsonify({"success": False, "message": "주문 내역을 찾을 수 없습니다."}), 404
        flash("주문 내역을 찾을 수 없습니다.", "warning")
        return redirect(url_for("main.index")), 404

    # 2. 본인 주문이 맞는지 확인 (다른 사용자의 order_id 접근 차단)
    order_user_id = str(order_data.get("user_id") or "")
    if order_user_id != str(user_id):
        if request.is_json:
            return jsonify({"success": False, "message": "접근 권한이 없습니다."}), 403
        abort(403, description="접근 권한이 없습니다.")

    # 3. 주문 상품 목록 (order_items) 조회
    formatted_items = []
    try:
        items_res = (
            db.table("order_items")
            .select("product_name, option_description, unit_price, quantity, total_price, product_id, product_option_id, products(product_images(image_url, is_primary))")
            .eq("order_id", order_id)
            .execute()
        )
        items_data = items_res.data if items_res else []

        # 세션 last_order의 이미지 캐시 활용
        session_img_map = {}
        last_order = session.get("last_order") or {}
        if last_order.get("order_id") == order_id:
            for s_it in last_order.get("order_items", []):
                if s_it.get("name") and s_it.get("image_url"):
                    session_img_map[s_it.get("name")] = s_it.get("image_url")

        for it in items_data:
            prod = it.get("products") or {}
            images = prod.get("product_images") or []
            img_url = None
            if images:
                for img in images:
                    if img.get("is_primary"):
                        img_url = img.get("image_url")
                        break
                if not img_url:
                    img_url = images[0].get("image_url")

            if not img_url and it.get("product_name") in session_img_map:
                img_url = session_img_map[it.get("product_name")]

            # DB product_images 추가 조회 시도
            if not img_url and it.get("product_id"):
                try:
                    p_imgs = db.table("product_images").select("image_url, is_primary").eq("product_id", it.get("product_id")).execute()
                    if p_imgs and p_imgs.data:
                        img_url = next((pi["image_url"] for pi in p_imgs.data if pi.get("is_primary")), p_imgs.data[0]["image_url"])
                except Exception:
                    pass

            unit_price = int(float(it.get("unit_price", 0)))
            quantity = int(it.get("quantity", 1))
            total_price = int(float(it.get("total_price") or (unit_price * quantity)))

            formatted_items.append({
                "name": it.get("product_name"),
                "product_name": it.get("product_name"),
                "option": it.get("option_description", "-"),
                "option_description": it.get("option_description", "-"),
                "quantity": quantity,
                "price": unit_price,
                "unit_price": unit_price,
                "total_price": total_price,
                "image_url": img_url
            })
    except Exception as e:
        print(f"[Order Complete View Error] order_items 조회 실패: {e}", file=sys.stderr)

    # 4. 일시 및 금액 계산
    created_at_raw = order_data.get("created_at", "")
    try:
        dt = datetime.datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        ordered_at_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ordered_at_str = created_at_raw[:19].replace("T", " ") if created_at_raw else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    t_goods = int(float(order_data.get("total_amount", 0)))
    f_amt = int(float(order_data.get("final_amount", 0)))
    d_amt = int(float(order_data.get("discount_amount", 0)))
    shipping_fee = max(0, f_amt - t_goods + d_amt)

    last_order = session.get("last_order") or {}
    if last_order.get("order_id") == order_id:
        pay_method = last_order.get("pay_method", "card")
        coupon_name = last_order.get("coupon_name")
        if last_order.get("shipping_fee") is not None:
            shipping_fee = last_order.get("shipping_fee")
    else:
        pay_method = "card"
        coupon_name = None

    order_info = {
        "order_id": order_data.get("id"),
        "id": order_data.get("id"),
        "order_number": order_data.get("order_number"),
        "ordered_at": ordered_at_str,
        "created_at": ordered_at_str,
        "status": order_data.get("status", "paid"),
        "status_text": "결제 완료" if order_data.get("status") in ("paid", "completed") else order_data.get("status"),
        "recipient_name": order_data.get("recipient_name"),
        "shipping_name": order_data.get("recipient_name"),
        "recipient_phone": order_data.get("recipient_phone"),
        "shipping_phone": order_data.get("recipient_phone"),
        "shipping_address": order_data.get("shipping_address"),
        "shipping_memo": order_data.get("memo") or "요청사항 없음",
        "memo": order_data.get("memo") or "요청사항 없음",
        "pay_method": pay_method,
        "coupon_name": coupon_name,
        "total_goods_price": t_goods,
        "total_amount": t_goods,
        "shipping_fee": shipping_fee,
        "discount_amount": d_amt,
        "final_amount": f_amt,
        "order_items": formatted_items
    }

    return render_template("order/complete.html", order=order_info)


@order_bp.route("/complete")
def order_complete():
    """모의 결제 완료 화면 호환 유지"""
    last_order = session.get("last_order")
    if last_order and last_order.get("order_id"):
        return redirect(url_for("order.order_complete_detail", order_id=last_order["order_id"]))
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
