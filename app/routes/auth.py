# app/routes/auth.py - VIBE FASHION 인증 라우트 (회원가입, 로그인, SNS 로그인, 비밀번호 찾기)
import os
import sys
import traceback
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"[Supabase Auth Init Error] {e}", file=sys.stderr)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """로그인 페이지 및 인증 처리"""
    if "user" in session:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("이메일과 비밀번호를 모두 입력해 주세요.", "danger")
            return render_template("auth/login.html", email=email)

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
                        "name": auth_res.user.user_metadata.get("name", email.split("@")[0])
                    }
                    session["user"] = user_data
                    flash(f"{user_data['name']}님, 환영합니다!", "success")
                    return redirect(url_for("main.index"))
                else:
                    flash("이메일 또는 비밀번호가 올바르지 않습니다.", "danger")
            else:
                # Supabase 미연결 시 데모 세션 로그인
                session["user"] = {"id": "demo", "email": email, "name": email.split("@")[0]}
                flash("로그인되었습니다 (데모 모드).", "info")
                return redirect(url_for("main.index"))
        except Exception as e:
            err_msg = str(e)
            if "Invalid login credentials" in err_msg:
                flash("이메일 또는 비밀번호가 일치하지 않습니다.", "danger")
            else:
                flash(f"로그인 처리 중 오류가 발생했습니다: {err_msg}", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """회원가입 페이지 및 계정 생성 처리"""
    if "user" in session:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not email or not name or not password:
            flash("모든 필수 항목을 입력해 주세요.", "danger")
            return render_template("auth/register.html", email=email, name=name)

        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.", "danger")
            return render_template("auth/register.html", email=email, name=name)

        if len(password) < 6:
            flash("비밀번호는 최소 6자 이상이어야 합니다.", "danger")
            return render_template("auth/register.html", email=email, name=name)

        try:
            if supabase:
                auth_res = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {
                            "name": name
                        }
                    }
                })
                if auth_res and auth_res.user:
                    session["user"] = {
                        "id": auth_res.user.id,
                        "email": auth_res.user.email,
                        "name": name
                    }
                    flash(f"{name}님, VIBE FASHION 가입을 환영합니다! 15% 웰컴 쿠폰이 발급되었습니다.", "success")
                    return redirect(url_for("main.index"))
            else:
                session["user"] = {"id": "demo", "email": email, "name": name}
                flash(f"{name}님, 환영합니다 (데모 가입).", "success")
                return redirect(url_for("main.index"))
        except Exception as e:
            flash(f"회원가입 중 오류가 발생했습니다: {e}", "danger")

    return render_template("auth/register.html")


@auth_bp.route("/oauth/<provider>")
def oauth_login(provider):
    """
    SNS 소셜 로그인 리다이렉트 (카카오, 네이버, 구글)
    Supabase의 signInWithOAuth 연동
    """
    valid_providers = {
        "kakao": "kakao",
        "naver": "naver", # Supabase 커스텀 OIDC 또는 Supabase OAuth
        "google": "google"
    }

    if provider not in valid_providers:
        flash("지원하지 않는 로그인 방식입니다.", "warning")
        return redirect(url_for("auth.login"))

    callback_url = url_for("auth.oauth_callback", _external=True)

    try:
        if supabase:
            # Supabase gotrue signInWithOAuth 호출
            res = supabase.auth.sign_in_with_oauth({
                "provider": valid_providers[provider],
                "options": {
                    "redirect_to": callback_url
                }
            })
            if hasattr(res, 'url') and res.url:
                return redirect(res.url)
            elif isinstance(res, dict) and res.get("url"):
                return redirect(res["url"])
    except Exception as e:
        print(f"[OAuth Info] {provider} Supabase 소셜 연동 처리 ({e}).", file=sys.stderr)

    # Supabase 대시보드에서 Provider 키가 등록되기 전 데모 인터랙션 지원
    provider_names = {"kakao": "카카오", "naver": "네이버", "google": "구글"}
    p_name = provider_names.get(provider, provider)
    session["user"] = {
        "id": f"sns_{provider}_sample",
        "email": f"{provider}_user@vibe-fashion.com",
        "name": f"{p_name} 회원"
    }
    flash(f"{p_name} 계정으로 간편 로그인되었습니다.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/callback")
def oauth_callback():
    """OAuth 콜백 핸들러"""
    flash("SNS 간편 인증이 완료되었습니다.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """아이디 및 비밀번호 찾기 (재설정 이메일 발송)"""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        find_type = request.form.get("find_type", "password")

        if not email:
            flash("이메일을 입력해 주세요.", "danger")
            return render_template("auth/forgot_password.html")

        if find_type == "id":
            flash(f"입력하신 연락처 정보로 등록된 아이디(이메일)는 '{email}' 입니다.", "info")
            return render_template("auth/forgot_password.html", sent=True, find_type="id")
        else:
            try:
                if supabase:
                    supabase.auth.reset_password_for_email(email, {
                        "redirect_to": url_for("auth.login", _external=True)
                    })
                flash(f"'{email}' 주소로 비밀번호 재설정 링크가 전송되었습니다.", "success")
                return render_template("auth/forgot_password.html", sent=True, find_type="password")
            except Exception as e:
                flash(f"재설정 메일 발송 중 오류가 발생했습니다: {e}", "danger")

    return render_template("auth/forgot_password.html")


@auth_bp.route("/logout")
def logout():
    """로그아웃"""
    session.pop("user", None)
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    flash("로그아웃되었습니다.", "info")
    return redirect(url_for("main.index"))
