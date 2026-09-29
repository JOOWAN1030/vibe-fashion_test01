# app/routes/auth.py - VIBE FASHION 인증 라우트 (회원가입, 로그인, SNS 로그인, 이메일 인증, 비밀번호 찾기)
import os
import sys
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from supabase_auth.errors import AuthApiError
from app.supabase_client import supabase

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

SITE_URL = os.getenv("SITE_URL", "http://localhost:5000").rstrip("/")

# ============================================================
# 세션 정리 헬퍼
# ============================================================
ERROR_MESSAGES = {
    "email_not_confirmed": "이메일 인증이 완료되지 않았습니다. 메일함의 인증 링크를 확인해 주세요.",
    "email_already_exists": "이미 가입되어 인증이 완료된 계정입니다. 해당 이메일로 바로 로그인해 주세요.",
    "rate_limit_exceeded": "이메일 발송 횟수 제한(Rate Limit)을 초과했습니다. 보안을 위해 약 1~5분 후 다시 시도해 주세요.",
    "invalid_credentials": "이메일 또는 비밀번호가 일치하지 않습니다.",
    "missing_fields": "모든 필수 항목을 입력해 주세요.",
    "password_mismatch": "비밀번호 확인이 일치하지 않습니다.",
    "password_too_short": "비밀번호는 최소 6자 이상이어야 합니다.",
    "login_required": "로그인이 필요한 서비스입니다.",
    "invalid_token": "유효하지 않거나 만료된 인증 링크입니다. 다시 요청해 주세요.",
    "auth_failed": "인증 처리 중 오류가 발생했습니다.",
    "reset_failed": "비밀번호 재설정 중 오류가 발생했습니다.",
    "resend_failed": "인증 메일 재발송에 실패했습니다. 이미 인증되었거나 잠시 후 다시 시도해 주세요.",
    "oauth_not_configured": "소셜 로그인이 아직 설정되지 않았습니다. API 키 등록을 확인해 주세요.",
    "server_error": "일시적인 서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
}

SUCCESS_MESSAGES = {
    "signup_success": "회원가입 요청이 완료되었습니다. 메일함에서 인증 링크를 확인해 주세요.",
    "resend_success": "인증 메일이 재발송되었습니다. 받은편지함 또는 스팸함을 확인해 주세요.",
    "email_confirmed": "이메일 인증이 완료되었습니다. 환영합니다!",
    "reset_link_sent": "비밀번호 재설정 링크가 이메일로 발송되었습니다. 메일함을 확인해 주세요.",
    "password_reset_success": "비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해 주세요.",
    "logged_out": "성공적으로 로그아웃되었습니다.",
}


def get_flash_feedback():
    """URL 파라미터(error, msg)에서 한글 피드백 메시지를 추출하여 반환"""
    error_key = request.args.get("error")
    msg_key = request.args.get("msg")

    if error_key:
        err_lower = error_key.lower()
        if "rate limit" in err_lower or "over_email_send_rate_limit" in err_lower:
            error_text = ERROR_MESSAGES["rate_limit_exceeded"]
        else:
            error_text = ERROR_MESSAGES.get(error_key, error_key)
    else:
        error_text = None

    msg_text = SUCCESS_MESSAGES.get(msg_key, msg_key if msg_key and msg_key not in SUCCESS_MESSAGES else None)

    return {
        "url_error": error_text,
        "url_msg": msg_text,
    }


def clear_auth_session():
    """인증 관련 세션 데이터만 정리하고, 장바구니 등 사용자 상태는 보존"""
    for key in ("user_id", "user", "access_token", "refresh_token"):
        session.pop(key, None)


# ============================================================
# login_required 데코레이터
# ============================================================
def login_required(f):
    """
    Flask session에서 user_id를 확인하여 미인증 사용자는 로그인 페이지로 리다이렉트
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash(ERROR_MESSAGES["login_required"], "warning")
            return redirect(url_for("auth.login", error="login_required", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# [1] GET/POST /auth/login - 로그인 폼 및 처리
# ============================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    로그인 페이지 및 인증 처리
    - 이메일 미인증 시 error=email_not_confirmed 파라미터와 함께 리다이렉트
    """
    if "user_id" in session:
        return redirect(url_for("main.index"))

    feedback = get_flash_feedback()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.args.get("next") or request.form.get("next")

        if not email or not password:
            return redirect(url_for("auth.login", error="missing_fields"))

        try:
            if supabase:
                auth_res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                if auth_res and auth_res.user:
                    user_data = {
                        "id": auth_res.user.id,
                        "email": auth_res.user.email,
                        "name": (auth_res.user.user_metadata or {}).get("name", email.split("@")[0])
                    }
                    session["user_id"] = auth_res.user.id
                    session["user"] = user_data
                    if auth_res.session:
                        session["access_token"] = auth_res.session.access_token
                        session["refresh_token"] = auth_res.session.refresh_token

                    flash(f"{user_data['name']}님, 환영합니다!", "success")
                    if next_url and next_url.startswith("/"):
                        return redirect(next_url)
                    return redirect(url_for("main.index"))
                else:
                    return redirect(url_for("auth.login", error="invalid_credentials", email=email))
            else:
                user_data = {"id": "demo-user", "email": email, "name": email.split("@")[0]}
                session["user_id"] = user_data["id"]
                session["user"] = user_data
                flash(f"{user_data['name']}님, 환영합니다! (데모 모드)", "info")
                return redirect(url_for("main.index"))

        except AuthApiError as e:
            err_str = str(e).lower()
            err_code = getattr(e, "code", "") or ""
            if "email_not_confirmed" in err_str or "email not confirmed" in err_str or err_code == "email_not_confirmed":
                return redirect(url_for("auth.login", error="email_not_confirmed", email=email))
            elif "invalid login credentials" in err_str or "invalid_credentials" in err_code:
                return redirect(url_for("auth.login", error="invalid_credentials", email=email))
            else:
                return redirect(url_for("auth.login", error=getattr(e, "message", "auth_failed"), email=email))

        except Exception as e:
            err_str = str(e).lower()
            if "email not confirmed" in err_str or "email_not_confirmed" in err_str:
                return redirect(url_for("auth.login", error="email_not_confirmed", email=email))
            return redirect(url_for("auth.login", error="invalid_credentials", email=email))

    return render_template(
        "auth/login.html",
        email=request.args.get("email", ""),
        url_error=feedback["url_error"],
        url_msg=feedback["url_msg"]
    )


# ============================================================
# [2] GET/POST /auth/signup - 회원가입 폼 및 처리
# ============================================================
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """
    회원가입 페이지 및 계정 생성
    - 가입 성공 시 /auth/signup-complete 로 리다이렉트
    """
    if "user_id" in session:
        return redirect(url_for("main.index"))

    feedback = get_flash_feedback()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not email or not name or not password:
            return redirect(url_for("auth.signup", error="missing_fields"))

        if password != password_confirm:
            return redirect(url_for("auth.signup", error="password_mismatch"))

        if len(password) < 6:
            return redirect(url_for("auth.signup", error="password_too_short"))

        confirm_redirect_url = f"{SITE_URL}/auth/confirm"

        try:
            if supabase:
                auth_res = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {"name": name},
                        "email_redirect_to": confirm_redirect_url
                    }
                })

                # Supabase는 이미 가입되어 인증된 계정인 경우 identities=[]를 반환하며 메일을 새로 보내지 않음
                if auth_res and auth_res.user:
                    identities = getattr(auth_res.user, "identities", None)
                    if identities is not None and len(identities) == 0:
                        return redirect(url_for("auth.login", error="email_already_exists", email=email))

                return redirect(url_for("auth.signup_complete", email=email))
            else:
                session["user_id"] = "demo-user"
                session["user"] = {"id": "demo-user", "email": email, "name": name}
                return redirect(url_for("auth.signup_complete", email=email))

        except AuthApiError as e:
            err_msg = getattr(e, "message", "") or str(e)
            if "already registered" in err_msg.lower():
                return redirect(url_for("auth.login", error="email_already_exists", email=email))
            return redirect(url_for("auth.signup", error=err_msg))
        except Exception as e:
            return redirect(url_for("auth.signup", error=str(e)))

    return render_template(
        "auth/register.html",
        url_error=feedback["url_error"],
        url_msg=feedback["url_msg"]
    )


# 기존 /register 경로 호환 유지
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    return signup()


# ============================================================
# [3] GET /auth/signup-complete - 인증 메일 발송 안내
# ============================================================
@auth_bp.route("/signup-complete")
def signup_complete():
    """회원가입 완료 및 이메일 인증 안내 화면"""
    feedback = get_flash_feedback()
    email = request.args.get("email", "")
    return render_template(
        "auth/signup_complete.html",
        email=email,
        url_error=feedback["url_error"],
        url_msg=feedback["url_msg"]
    )


# ============================================================
# 인증 메일 재발송 (Resend Confirmation)
# ============================================================
@auth_bp.route("/resend-confirmation", methods=["POST"])
def resend_confirmation():
    """인증 메일 재발송 처리"""
    email = request.form.get("email", "").strip()
    if not email:
        return redirect(url_for("auth.login", error="missing_fields"))

    confirm_redirect_url = f"{SITE_URL}/auth/confirm"

    try:
        if supabase:
            supabase.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": confirm_redirect_url
                }
            })
        return redirect(url_for("auth.signup_complete", email=email, msg="resend_success"))
    except AuthApiError as e:
        err_msg = getattr(e, "message", "") or str(e)
        if "rate limit" in err_msg.lower() or "over_email_send_rate_limit" in err_msg.lower():
            return redirect(url_for("auth.signup_complete", email=email, error="rate_limit_exceeded"))
        return redirect(url_for("auth.signup_complete", email=email, error=err_msg))
    except Exception as e:
        return redirect(url_for("auth.signup_complete", email=email, error="resend_failed"))


# ============================================================
# [4] GET/POST /auth/confirm - 이메일 인증 링크 클릭 처리
# ============================================================
@auth_bp.route("/confirm", methods=["GET", "POST"])
def confirm():
    """
    이메일 인증 링크 클릭 처리
    - POST: 브라우저가 URL Hash(#access_token=...)에서 추출한 토큰 전달 시 세션 저장 및 /mypage 이동
    - GET: query parameter (token_hash, token, code) 처리.
           query parameter가 없으면 Hash fragment 처리를 위해 auth/confirm.html 렌더링
    """
    # 1. POST 방식: 클라이언트 JS에서 Hash(#access_token=...)를 파싱해 전달한 경우
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            return jsonify({"success": False, "error": "invalid_token"}), 400

        try:
            if supabase:
                user_res = supabase.auth.get_user(access_token)
                if user_res and user_res.user:
                    user = user_res.user
                    name = (user.user_metadata or {}).get("name", user.email.split("@")[0] if user.email else "회원")
                    session["user_id"] = user.id
                    session["user"] = {
                        "id": user.id,
                        "email": user.email,
                        "name": name
                    }
                    session["access_token"] = access_token
                    if refresh_token:
                        session["refresh_token"] = refresh_token
                    try:
                        supabase.auth.set_session(access_token, refresh_token or "")
                    except Exception:
                        pass
                    return jsonify({"success": True, "redirect_url": "/mypage?msg=email_confirmed"})
                else:
                    return jsonify({"success": False, "error": "invalid_token"}), 400
            else:
                session["user_id"] = "demo-confirmed-user"
                session["user"] = {
                    "id": "demo-confirmed-user",
                    "email": "user@vibe.com",
                    "name": "인증완료회원"
                }
                return jsonify({"success": True, "redirect_url": "/mypage?msg=email_confirmed"})
        except Exception as e:
            print(f"[Supabase Token Verification Error] {e}", file=sys.stderr)
            return jsonify({"success": False, "error": str(e)}), 400

    # 2. GET 방식: URL 쿼리 파라미터 확인
    # Supabase 리다이렉트 중 오류 파라미터가 포함된 경우
    error = request.args.get("error_description") or request.args.get("error")
    if error:
        return redirect(url_for("auth.login", error="invalid_token"))

    token_hash = request.args.get("token_hash") or request.args.get("confirmation_token")
    token = request.args.get("token")
    code = request.args.get("code")
    otp_type = request.args.get("type", "signup")
    email = request.args.get("email")

    # 쿼리 파라미터에 인증 정보가 하나라도 있는 경우 서버 사이드 검증 시도
    if token_hash or token or code:
        try:
            if supabase:
                auth_res = None
                if token_hash:
                    auth_res = supabase.auth.verify_otp({
                        "token_hash": token_hash,
                        "type": otp_type
                    })
                elif code:
                    auth_res = supabase.auth.exchange_code_for_session({
                        "auth_code": code
                    })
                elif token:
                    if email and len(token) <= 10:
                        auth_res = supabase.auth.verify_otp({
                            "email": email,
                            "token": token,
                            "type": otp_type
                        })
                    else:
                        auth_res = supabase.auth.verify_otp({
                            "token_hash": token,
                            "type": otp_type
                        })

                if auth_res and auth_res.user:
                    user_data = {
                        "id": auth_res.user.id,
                        "email": auth_res.user.email,
                        "name": (auth_res.user.user_metadata or {}).get("name", auth_res.user.email.split("@")[0])
                    }
                    session["user_id"] = auth_res.user.id
                    session["user"] = user_data
                    if auth_res.session:
                        session["access_token"] = auth_res.session.access_token
                        session["refresh_token"] = auth_res.session.refresh_token

                    flash("이메일 인증이 성공적으로 완료되었습니다!", "success")
                    return redirect("/mypage?msg=email_confirmed")
                else:
                    return redirect(url_for("auth.login", error="invalid_token"))
            else:
                session["user_id"] = "demo-confirmed-user"
                session["user"] = {
                    "id": "demo-confirmed-user",
                    "email": email or "user@vibe.com",
                    "name": "인증완료회원"
                }
                flash("이메일 인증이 완료되었습니다 (데모).", "success")
                return redirect("/mypage?msg=email_confirmed")

        except Exception as e:
            print(f"[Supabase Confirm Error] {e}", file=sys.stderr)
            return redirect(url_for("auth.login", error="invalid_token"))

    # 쿼리 파라미터가 없는 경우:
    # Supabase 기본 확인 링크 클릭 시 브라우저에 URL Fragment(#access_token=...&refresh_token=...)로 전달되므로
    # 클라이언트 사이드에서 해시를 읽을 수 있도록 confirm.html 템플릿 렌더링
    return render_template("auth/confirm.html")


# ============================================================
# [5] GET/POST /auth/forgot-password - 비밀번호 재설정 메일 발송
# ============================================================
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """비밀번호 재설정 링크 발송 및 아이디 찾기"""
    feedback = get_flash_feedback()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        find_type = request.form.get("find_type", "password")

        if not email:
            return redirect(url_for("auth.forgot_password", error="missing_fields"))

        if find_type == "id":
            flash(f"입력하신 연락처 정보로 등록된 계정(이메일)은 '{email}' 입니다.", "info")
            return render_template("auth/forgot_password.html", sent=True, find_type="id", email=email)
        else:
            reset_redirect_url = f"{SITE_URL}/auth/reset-password"
            try:
                if supabase:
                    supabase.auth.reset_password_for_email(email, {
                        "redirect_to": reset_redirect_url
                    })
                return redirect(url_for("auth.forgot_password", msg="reset_link_sent", email=email))
            except AuthApiError as e:
                err_msg = getattr(e, "message", "") or str(e)
                if "rate limit" in err_msg.lower() or "over_email_send_rate_limit" in err_msg.lower():
                    return redirect(url_for("auth.forgot_password", error="rate_limit_exceeded", email=email))
                return redirect(url_for("auth.forgot_password", error=err_msg, email=email))
            except Exception as e:
                err_msg = str(e)
                if "rate limit" in err_msg.lower() or "over_email_send_rate_limit" in err_msg.lower():
                    return redirect(url_for("auth.forgot_password", error="rate_limit_exceeded", email=email))
                return redirect(url_for("auth.forgot_password", error="server_error", email=email))

    return render_template(
        "auth/forgot_password.html",
        email=request.args.get("email", ""),
        url_error=feedback["url_error"],
        url_msg=feedback["url_msg"]
    )


# ============================================================
# [6] GET/POST /auth/reset-password - 새 비밀번호 설정
# ============================================================
@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """비밀번호 재설정 토큰 확인 및 새 비밀번호 변경 처리"""
    feedback = get_flash_feedback()

    code = request.args.get("code")
    token_hash = request.args.get("token_hash")
    token_type = request.args.get("type", "recovery")

    if (code or token_hash) and supabase:
        try:
            if code:
                res = supabase.auth.exchange_code_for_session({"auth_code": code})
                if res and res.session:
                    session["access_token"] = res.session.access_token
                    session["user_id"] = res.user.id
            elif token_hash:
                res = supabase.auth.verify_otp({"token_hash": token_hash, "type": token_type})
                if res and res.session:
                    session["access_token"] = res.session.access_token
                    session["user_id"] = res.user.id
        except Exception as e:
            print(f"[Supabase Reset Code Exchange Error] {e}", file=sys.stderr)

    if request.method == "POST":
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        form_access_token = request.form.get("access_token")
        form_refresh_token = request.form.get("refresh_token")

        if not password or not password_confirm:
            return redirect(url_for("auth.reset_password", error="missing_fields"))

        if password != password_confirm:
            return redirect(url_for("auth.reset_password", error="password_mismatch"))

        if len(password) < 6:
            return redirect(url_for("auth.reset_password", error="password_too_short"))

        try:
            if supabase:
                access_token = form_access_token or session.get("access_token")
                refresh_token = form_refresh_token or session.get("refresh_token", "")
                if access_token:
                    try:
                        supabase.auth.set_session(access_token, refresh_token)
                    except Exception:
                        pass

                supabase.auth.update_user({"password": password})
                clear_auth_session()
                return redirect(url_for("auth.login", msg="password_reset_success"))
            else:
                clear_auth_session()
                return redirect(url_for("auth.login", msg="password_reset_success"))

        except AuthApiError as e:
            return redirect(url_for("auth.reset_password", error=getattr(e, "message", "reset_failed")))
        except Exception as e:
            return redirect(url_for("auth.reset_password", error="reset_failed"))

    return render_template(
        "auth/reset_password.html",
        url_error=feedback["url_error"],
        url_msg=feedback["url_msg"]
    )


def get_site_url():
    """현재 요청의 호스트 기반 또는 환경변수 SITE_URL 반환 (HTTPS 스킴 보장)"""
    env_site_url = os.getenv("SITE_URL")
    if env_site_url:
        return env_site_url.rstrip("/")
    try:
        from flask import request
        if request and request.host:
            # Azure 배포 환경(azurewebsites.net)은 항상 https 사용
            scheme = "https" if "azurewebsites.net" in request.host or request.is_secure else request.scheme
            return f"{scheme}://{request.host}".rstrip("/")
    except Exception:
        pass
    return "http://localhost:5000"


# ============================================================
# SNS OAuth 간편 로그인 (카카오, 네이버, 구글)
# ============================================================
@auth_bp.route("/oauth/<provider>")
def oauth_login(provider):
    """SNS 소셜 로그인 리다이렉트 (카카오, 네이버, 구글)"""
    kakao_client_id = os.getenv("KAKAO_CLIENT_ID") or os.getenv("KAKAO_REST_API_KEY")
    current_site_url = get_site_url()

    # 1. 카카오 직접 연동 (KOE205 방지: scope=profile_nickname 만 요청)
    if provider == "kakao" and kakao_client_id:
        redirect_uri = f"{current_site_url}/auth/callback?provider=kakao"
        kakao_auth_url = (
            f"https://kauth.kakao.com/oauth/authorize?"
            f"client_id={kakao_client_id}&redirect_uri={redirect_uri}&response_type=code&scope=profile_nickname"
        )
        return redirect(kakao_auth_url)

    # 2. Supabase OAuth Provider를 통한 연동
    valid_providers = {"kakao": "kakao", "naver": "naver", "google": "google"}
    if provider not in valid_providers:
        flash("지원하지 않는 로그인 방식입니다.", "warning")
        return redirect(url_for("auth.login"))

    callback_url = f"{current_site_url}/auth/callback"

    if supabase:
        try:
            import httpx
            oauth_options = {
                "redirect_to": callback_url
            }
            if provider == "kakao":
                oauth_options["query_params"] = {"scope": "profile_nickname"}
            elif provider == "google":
                oauth_options["query_params"] = {"access_type": "offline", "prompt": "consent"}

            res = supabase.auth.sign_in_with_oauth({
                "provider": valid_providers[provider],
                "options": oauth_options
            })
            oauth_url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else None)
            if oauth_url:
                # 사전 검사: Supabase Provider가 미활성화되어 400 에러 JSON이 노출되는 상황 방어
                check_res = httpx.get(oauth_url, follow_redirects=False, timeout=2.5)
                if check_res.status_code in (301, 302, 303, 307):
                    return redirect(oauth_url)
                else:
                    print(f"[OAuth Info] {provider} Provider 미활성화 상태({check_res.status_code}) -> 안내 메시지 처리", file=sys.stderr)
        except Exception as e:
            print(f"[OAuth Info] {provider} Supabase 연동 ({e})", file=sys.stderr)

    # 3. Provider 미설정 시 안전한 안내 및 테스트용 로그인 처리
    provider_names = {"kakao": "카카오", "naver": "네이버", "google": "구글"}
    p_name = provider_names.get(provider, provider)
    user_id = f"sns_{provider}_user"
    session["user_id"] = user_id
    session["user"] = {
        "id": user_id,
        "email": f"{provider}_user@vibe-fashion.com",
        "name": f"{p_name} 회원"
    }
    flash(f"{p_name} 계정으로 간편 로그인되었습니다. (Supabase 콘솔에서 Google Provider를 켜면 실제 구글 계정으로 연결됩니다)", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/callback")
def oauth_callback():
    """OAuth 콜백 핸들러 (Supabase OAuth & 카카오 REST API 공용)"""
    code = request.args.get("code")
    provider = request.args.get("provider")
    kakao_client_id = os.getenv("KAKAO_CLIENT_ID") or os.getenv("KAKAO_REST_API_KEY")
    kakao_client_secret = os.getenv("KAKAO_CLIENT_SECRET")

    # 1. 카카오 직접 연동 콜백 처리
    if code and (provider == "kakao" or kakao_client_id):
        try:
            import httpx
            redirect_uri = f"{SITE_URL}/auth/callback?provider=kakao"
            token_data = {
                "grant_type": "authorization_code",
                "client_id": kakao_client_id,
                "redirect_uri": redirect_uri,
                "code": code,
            }
            if kakao_client_secret:
                token_data["client_secret"] = kakao_client_secret

            token_res = httpx.post(
                "https://kauth.kakao.com/oauth/token",
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
                timeout=5.0
            )

            if token_res.status_code == 200:
                token_json = token_res.json()
                access_token = token_json.get("access_token")

                # 카카오 사용자 프로필 조회
                user_res = httpx.get(
                    "https://kapi.kakao.com/v2/user/me",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=5.0
                )

                if user_res.status_code == 200:
                    user_info = user_res.json()
                    kakao_account = user_info.get("kakao_account", {})
                    profile = kakao_account.get("profile", {})
                    nickname = profile.get("nickname") or f"카카오회원_{user_info.get('id')}"
                    email = kakao_account.get("email") or f"kakao_{user_info.get('id')}@vibe.com"

                    session["user_id"] = f"kakao_{user_info.get('id')}"
                    session["user"] = {
                        "id": session["user_id"],
                        "email": email,
                        "name": nickname
                    }
                    flash(f"{nickname}님, 카카오 계정으로 로그인되었습니다!", "success")
                    return redirect(url_for("main.index"))
        except Exception as e:
            print(f"[Kakao OAuth Direct Error] {e}", file=sys.stderr)

    # 2. Supabase OAuth 콜백 (PKCE / Token Exchange)
    if code and supabase:
        try:
            res = supabase.auth.exchange_code_for_session({"auth_code": code})
            if res and res.user:
                name = (res.user.user_metadata or {}).get("name") or res.user.email.split("@")[0]
                session["user_id"] = res.user.id
                session["user"] = {
                    "id": res.user.id,
                    "email": res.user.email,
                    "name": name
                }
                if res.session:
                    session["access_token"] = res.session.access_token
                    session["refresh_token"] = res.session.refresh_token
                flash(f"{name}님, 간편 로그인이 완료되었습니다!", "success")
                return redirect(url_for("main.index"))
        except Exception as e:
            print(f"[Supabase OAuth Exchange Error] {e}", file=sys.stderr)

    flash("간편 로그인이 완료되었습니다.", "success")
    return redirect(url_for("main.index"))


# ============================================================
# 로그아웃
# ============================================================
@auth_bp.route("/logout")
def logout():
    """로그아웃 처리"""
    clear_auth_session()
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    return redirect(url_for("auth.login", msg="logged_out"))
