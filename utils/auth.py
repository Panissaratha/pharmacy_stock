from __future__ import annotations

import hashlib

import streamlit as st


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _get_credentials() -> dict:
    # st.secrets raises if no secrets.toml file exists at all (not just an
    # empty/missing key), so this must be guarded rather than using `in`/`.get`.
    try:
        return dict(st.secrets.get("credentials", {}))
    except Exception:
        return {}


def check_login(username: str, password: str) -> dict | None:
    users = _get_credentials()
    user = users.get(username)
    if user and hash_password(password) == user.get("password_hash"):
        return {"username": username, "name": user.get("name", username)}
    return None


def _remember_token(username: str, password_hash: str) -> str:
    # ไม่เก็บรหัสผ่านจริงไว้ใน URL — ใช้ hash ที่ผูกกับ username+password_hash แทน
    # เพื่อให้ token นี้ใช้ยืนยันตัวตนแทนการ login ได้ แต่ย้อนกลับไปเป็นรหัสผ่านไม่ได้
    return hashlib.sha256(f"{username}:{password_hash}:remember".encode("utf-8")).hexdigest()


def _try_auto_login() -> None:
    remembered_username = st.query_params.get("u")
    remembered_token = st.query_params.get("t")
    if not remembered_username or not remembered_token:
        return
    users = _get_credentials()
    stored_user = users.get(remembered_username)
    if not stored_user:
        return
    expected_token = _remember_token(remembered_username, stored_user.get("password_hash", ""))
    if expected_token == remembered_token:
        st.session_state.user = {
            "username": remembered_username,
            "name": stored_user.get("name", remembered_username),
        }


def is_logged_in() -> bool:
    if "user" not in st.session_state:
        _try_auto_login()
    return "user" in st.session_state


def logout() -> None:
    st.session_state.pop("user", None)
    st.query_params.pop("u", None)
    st.query_params.pop("t", None)
    st.rerun()


def login_form() -> None:
    st.title("💊 เข้าสู่ระบบ")
    st.caption("ระบบนับสต็อกร้านขายยา")

    if not _get_credentials():
        st.warning(
            "ยังไม่ได้ตั้งค่าผู้ใช้งานใน .streamlit/secrets.toml "
            "กรุณาดูตัวอย่างที่ secrets.toml.example"
        )

    with st.form("login_form"):
        username = st.text_input("ชื่อผู้ใช้")
        password = st.text_input("รหัสผ่าน", type="password")
        remember_me = st.checkbox("จดจำฉันไว้ในเครื่องนี้", value=True)
        submitted = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)

    if submitted:
        user = check_login(username.strip(), password)
        if user:
            st.session_state.user = user
            if remember_me:
                stored_user = _get_credentials().get(user["username"], {})
                st.query_params["u"] = user["username"]
                st.query_params["t"] = _remember_token(
                    user["username"], stored_user.get("password_hash", "")
                )
            st.rerun()
        else:
            st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
