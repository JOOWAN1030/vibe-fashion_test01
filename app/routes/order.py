# app/routes/order.py - VIBE STORE 장바구니 및 모의 주문/결제 라우트
import os
import sys
import uuid
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

order_bp = Blueprint("order", __name__, url_prefix="/order")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase Order Init Error] {e}", file=sys.stderr)


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
    data = request.get_json() if request.is_json else request.form
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
    """장바구니 페이지"""
    cart = get_cart()
    totals = calculate_cart_totals(cart)
    return render_template("order/cart.html", cart=cart, totals=totals)


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
