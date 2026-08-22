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


def is_logged_in() -> bool:
    return "user" in st.session_state


def logout() -> None:
    st.session_state.pop("user", None)
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
        submitted = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)

    if submitted:
        user = check_login(username.strip(), password)
        if user:
            st.session_state.user = user
            st.rerun()
        else:
            st.error("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
