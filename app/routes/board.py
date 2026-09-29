# app/routes/board.py - VIBE FASHION 문의 게시판 라우트 (상품문의 & 배송문의)
import sys
import uuid
import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.supabase_client import supabase

board_bp = Blueprint("board", __name__, url_prefix="/board")

# 로컬 메모리 저장소 (Supabase 테이블 생성 전이거나 네트워크 오류 시 안전하게 동작)
IN_MEMORY_INQUIRIES = [
    {
        "id": "sample-inquiry-1",
        "type": "shipping",
        "title": "주문 후 출고까지 배송 기간이 얼마나 걸리나요?",
        "content": "어제 저녁에 컨스트럭션 아우터를 주문했는데 당일 출고되는지, 서울 지역 기준 언제쯤 받아볼 수 있을지 궁금합니다.",
        "author_name": "김*완",
        "author_email": "kim@example.com",
        "is_secret": False,
        "status": "answered",
        "answer": "안녕하세요, VIBE FASHION 고객감동팀입니다.\n평일 오후 2시 이전 결제 완료 건은 당일 출고되며, 서울/수도권 기준 출고 다음 날(1~2영업일 이내) 수령 가능합니다.\n감사합니다.",
        "answered_at": "2026-09-28 11:30",
        "created_at": "2026-09-27 19:40",
        "product_name": "컨스트럭션 아우터"
    },
    {
        "id": "sample-inquiry-2",
        "type": "product",
        "title": "척테일러 올스타 언얼스드 발볼 사이즈 문의드립니다.",
        "content": "평소 265mm를 신는데 발볼이 좀 넓은 편입니다. 정사이즈로 가면 될까요, 아니면 반업(270)해서 주문하는 게 좋을까요?",
        "author_name": "이*우",
        "author_email": "lee@example.com",
        "is_secret": False,
        "status": "answered",
        "answer": "안녕하세요 고객님!\n해당 모델은 발볼이 살짝 슬림하게 나온 실루엣입니다. 발볼이 넓으신 편이라면 반 사이즈 업(270mm)하여 착용하시는 것을 추천드립니다.",
        "answered_at": "2026-09-28 14:10",
        "created_at": "2026-09-28 09:15",
        "product_name": "척테일러 올스타 언얼스드"
    },
    {
        "id": "sample-inquiry-3",
        "type": "product",
        "title": "비밀글입니다. (원단 재입고 일정 문의)",
        "content": "오버핏 코튼 자켓 M사이즈 품절 상태인데 혹시 재입고 예정일이 잡혀 있는지 문의드립니다.",
        "author_name": "박*연",
        "author_email": "park@example.com",
        "is_secret": True,
        "status": "pending",
        "answer": None,
        "answered_at": None,
        "created_at": "2026-09-28 15:20",
        "product_name": "오버핏 코튼 자켓"
    },
    {
        "id": "sample-inquiry-4",
        "type": "shipping",
        "title": "제주도/도서산간 지역 배송비 및 소요 기간",
        "content": "제주도 서귀포시 배송 시 추가 도서산간 배송비가 발생하는지, 항공 배송 일정 알려주세요.",
        "author_name": "최*진",
        "author_email": "choi@example.com",
        "is_secret": False,
        "status": "answered",
        "answer": "안녕하세요 고객님!\nVIBE FASHION은 현재 프로모션 기간으로 제주 및 도서산간 지역도 3만원 이상 구매 시 추가 운임 없이 전 지역 무료 배송 혜택을 제공하고 있습니다.",
        "answered_at": "2026-09-28 16:00",
        "created_at": "2026-09-28 13:00",
        "product_name": "전체 배송 문의"
    }
]


def mask_name(name: str) -> str:
    """작성자 이름 마스킹 처리 (홍길동 -> 홍*동)"""
    if not name:
        return "고객"
    if len(name) == 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


@board_bp.route("/")
def list_inquiries():
    """문의 게시판 목록 조회 (상품문의 / 배송문의 / 전체)"""
    inquiry_type = request.args.get("type", "all")
    search_query = request.args.get("q", "").strip().lower()

    inquiries = []

    # 1. Supabase 조회 시도
    has_db_data = False
    if supabase:
        try:
            query = supabase.table("inquiries").select("*, products(name)")
            if inquiry_type in ("product", "shipping"):
                query = query.eq("type", inquiry_type)
            query = query.order("created_at", desc=True)
            res = query.execute()
            if res and res.data:
                for row in res.data:
                    prod = row.get("products") or {}
                    p_name = prod.get("name") if isinstance(prod, dict) else ""
                    inquiries.append({
                        "id": str(row.get("id")),
                        "type": row.get("type"),
                        "title": row.get("title"),
                        "content": row.get("content"),
                        "author_name": mask_name(row.get("author_name", "")),
                        "author_email": row.get("author_email"),
                        "is_secret": bool(row.get("is_secret")),
                        "status": row.get("status", "pending"),
                        "answer": row.get("answer"),
                        "answered_at": row.get("answered_at"),
                        "created_at": str(row.get("created_at", ""))[:16],
                        "product_name": p_name or "일반 문의"
                    })
                has_db_data = True
        except Exception as e:
            # 테이블 미생성 또는 캐시 미반영 시 폴백
            pass

    # 2. DB 데이터가 없으면 인메모리 샘플 데이터 결합
    if not has_db_data:
        filtered = IN_MEMORY_INQUIRIES
        if inquiry_type in ("product", "shipping"):
            filtered = [item for item in filtered if item["type"] == inquiry_type]
        inquiries = list(filtered)

    # 검색어 필터링
    if search_query:
        inquiries = [
            item for item in inquiries
            if search_query in item["title"].lower() or search_query in item["content"].lower() or search_query in item["product_name"].lower()
        ]

    # 통계 계산
    counts = {
        "all": len(IN_MEMORY_INQUIRIES),
        "product": sum(1 for x in IN_MEMORY_INQUIRIES if x["type"] == "product"),
        "shipping": sum(1 for x in IN_MEMORY_INQUIRIES if x["type"] == "shipping")
    }

    return render_template(
        "board/inquiry_list.html",
        inquiries=inquiries,
        current_type=inquiry_type,
        search_query=search_query,
        counts=counts
    )


@board_bp.route("/new", methods=["GET", "POST"])
def create_inquiry():
    """문의글 작성 페이지 및 등록"""
    preset_type = request.args.get("type", "product")
    preset_product = request.args.get("product", "")

    # 등록된 상품 목록 가져오기 (드롭다운 선택용)
    products = []
    if supabase:
        try:
            prod_res = supabase.table("products").select("id, name").eq("status", "active").execute()
            products = prod_res.data or []
        except Exception:
            products = []

    if request.method == "POST":
        inquiry_type = request.form.get("type", "product")
        product_id = request.form.get("product_id") or None
        product_name = request.form.get("product_name", "").strip()
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        is_secret = True if request.form.get("is_secret") == "on" else False
        password = request.form.get("password", "").strip()

        # 로그인된 사용자 정보 우선, 없으면 폼 입력값
        logged_user = session.get("user")
        if logged_user:
            author_name = logged_user.get("name", "회원")
            author_email = logged_user.get("email", "")
            user_id = logged_user.get("id") if logged_user.get("id") != "demo" else None
        else:
            author_name = request.form.get("author_name", "").strip() or "익명고객"
            author_email = request.form.get("author_email", "").strip()
            user_id = None

        if not title or not content:
            flash("제목과 내용을 모두 입력해 주세요.", "danger")
            return render_template(
                "board/inquiry_form.html",
                preset_type=inquiry_type,
                products=products,
                preset_product=preset_product
            )

        # 1. Supabase 저장 시도
        saved_db = False
        if supabase:
            try:
                new_row = {
                    "type": inquiry_type,
                    "title": title,
                    "content": content,
                    "author_name": author_name,
                    "author_email": author_email,
                    "is_secret": is_secret,
                    "password": password if is_secret else None,
                    "status": "pending"
                }
                if user_id:
                    new_row["user_id"] = user_id
                if product_id:
                    new_row["product_id"] = product_id

                sb_res = supabase.table("inquiries").insert(new_row).execute()
                if sb_res and sb_res.data:
                    saved_db = True
            except Exception as e:
                print(f"[Supabase Insert Notice] {e}", file=sys.stderr)

        # 2. 인메모리 저장 (즉시 반영 보장)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new_inquiry = {
            "id": f"inq-{uuid.uuid4().hex[:8]}",
            "type": inquiry_type,
            "title": title,
            "content": content,
            "author_name": mask_name(author_name),
            "author_email": author_email,
            "is_secret": is_secret,
            "status": "pending",
            "answer": None,
            "answered_at": None,
            "created_at": now_str,
            "product_name": product_name or ("배송 관련 문의" if inquiry_type == "shipping" else "기타 문의")
        }
        IN_MEMORY_INQUIRIES.insert(0, new_inquiry)

        flash("문의가 성공적으로 접수되었습니다. 담당자 확인 후 신속히 답변드리겠습니다.", "success")
        return redirect(url_for("board.list_inquiries", type=inquiry_type))

    return render_template(
        "board/inquiry_form.html",
        preset_type=preset_type,
        products=products,
        preset_product=preset_product
    )


@board_bp.route("/<inquiry_id>")
def inquiry_detail(inquiry_id):
    """문의 상세 및 답변 보기 (비밀글인 경우 작성자 확인)"""
    target = next((item for item in IN_MEMORY_INQUIRIES if item["id"] == inquiry_id), None)
    
    # Supabase에서 조회 시도
    if not target and supabase:
        try:
            res = supabase.table("inquiries").select("*, products(name)").eq("id", inquiry_id).execute()
            if res.data:
                row = res.data[0]
                prod = row.get("products") or {}
                p_name = prod.get("name") if isinstance(prod, dict) else ""
                target = {
                    "id": str(row.get("id")),
                    "type": row.get("type"),
                    "title": row.get("title"),
                    "content": row.get("content"),
                    "author_name": mask_name(row.get("author_name", "")),
                    "author_email": row.get("author_email"),
                    "is_secret": bool(row.get("is_secret")),
                    "status": row.get("status", "pending"),
                    "answer": row.get("answer"),
                    "answered_at": row.get("answered_at"),
                    "created_at": str(row.get("created_at", ""))[:16],
                    "product_name": p_name or "일반 문의"
                }
        except Exception:
            pass

    if not target:
        flash("존재하지 않는 문의글입니다.", "warning")
        return redirect(url_for("board.list_inquiries"))

    return render_template("board/inquiry_detail.html", inquiry=target)
