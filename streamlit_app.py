from __future__ import annotations

import streamlit as st

from utils import auth
from utils.sheets import (
    MASTER_COLUMNS,
    SheetNotConfiguredError,
    append_count,
    find_by_barcode,
    find_latest_count,
    load_all_counts,
    load_master_data,
    load_recent_counts,
)

st.set_page_config(page_title="นับสต็อกร้านยา", page_icon="💊", layout="centered")

if not auth.is_logged_in():
    auth.login_form()
    st.stop()

user = st.session_state.user

with st.sidebar:
    st.write(f"ผู้ใช้งาน: **{user['name']}**")
    if st.button("ออกจากระบบ", width="stretch"):
        auth.logout()
    st.divider()
    if st.button("🔄 อัพเดตข้อมูลยา", width="stretch"):
        load_master_data.clear()
        st.success("อัพเดตข้อมูลยาแล้ว")

st.title("💊 นับสต็อกร้านขายยา")

try:
    master_df = load_master_data()
except SheetNotConfiguredError as e:
    st.warning(
        f"⚠️ {e}\n\n"
        "กรุณาตั้งค่าไฟล์ `.streamlit/secrets.toml` ก่อนใช้งาน "
        "(ดูตัวอย่างที่ `secrets.toml.example` และ `README.md`)"
    )
    st.stop()
except Exception as e:  # noqa: BLE001
    st.error(f"เชื่อมต่อ Google Sheet ไม่สำเร็จ: {e}")
    st.stop()

if master_df.empty:
    st.info("ยังไม่มีข้อมูลยาในชีต MasterData")

if "matches" not in st.session_state:
    st.session_state.matches = None
    st.session_state.scanned_barcode = ""

# --- ขั้นตอนที่ 1: สแกน / กรอกบาร์โค้ด ---
with st.form("barcode_form", clear_on_submit=True):
    barcode_input = st.text_input("📷 สแกน หรือ กรอกเลขบาร์โค้ด", key="barcode_field")
    scan_submit = st.form_submit_button("ค้นหา", width="stretch")

if scan_submit and barcode_input.strip():
    matches = find_by_barcode(master_df, barcode_input)
    if matches.empty:
        st.error(f"ไม่พบยาที่มีบาร์โค้ด: {barcode_input}")
        st.session_state.matches = None
    else:
        st.session_state.matches = matches
        st.session_state.scanned_barcode = barcode_input.strip()

# ให้เคอร์เซอร์กลับไปที่ช่องบาร์โค้ดอัตโนมัติ เพื่อสแกนชิ้นถัดไปได้ทันที
st.html(
    """
    <script>
    const inputs = document.querySelectorAll('input[type="text"]');
    if (inputs.length > 0) { inputs[0].focus(); }
    </script>
    """,
    unsafe_allow_javascript=True,
)

# --- ขั้นตอนที่ 2: แสดงข้อมูลยา และกรอกจำนวนนับ ---
matches = st.session_state.matches
if matches is not None and not matches.empty:
    product_code_col = MASTER_COLUMNS["product_code"]
    name_col = MASTER_COLUMNS["name"]
    unit_col = MASTER_COLUMNS["unit"]
    lot_col = MASTER_COLUMNS["lot"]
    expiry_col = MASTER_COLUMNS["expiry"]

    st.divider()
    st.subheader(f"ชื่อยา: {matches.iloc[0][name_col]}")
    st.write(f"รหัสสินค้า: **{matches.iloc[0][product_code_col]}**")
    st.write(f"หน่วยนับ: **{matches.iloc[0][unit_col]}**")

    if len(matches) > 1:
        st.error("มีหลายล็อต ให้เลือกล็อตก่อนนับ")
        options = [
            f"ล็อต {row[lot_col]} — หมดอายุ {row[expiry_col]}"
            for _, row in matches.iterrows()
        ]
        selected = st.selectbox("เลือกเลขล็อต / วันหมดอายุ", options)
        selected_row = matches.iloc[options.index(selected)]
        
    else:
        st.error("มีล็อตเดียว")
        selected_row = matches.iloc[0]
        st.write(
            f"เลขที่ล็อต: **{selected_row[lot_col]}**  |  "
            f"วันหมดอายุ: **{selected_row[expiry_col]}**"
        )
        
    lot_value = str(selected_row[lot_col])
    try:
        existing = find_latest_count(
            load_all_counts(), st.session_state.scanned_barcode, lot_value
        )
    except Exception:  # noqa: BLE001
        existing = None

    if existing:
        st.caption("เคยนับไปแล้ว — แก้ไขแล้วบันทึกซ้ำได้")

    # คีย์ของ widget ต้องผูกกับบาร์โค้ด+ล็อต เพื่อให้ค่าที่กรอกไม่ตกค้าง
    # ข้ามไปยังยาตัวถัดไปเมื่อสแกนรายการใหม่โดยยังไม่ได้บันทึก
    item_key = f"{st.session_state.scanned_barcode}__{lot_value}"

    col1, col2 = st.columns(2)
    with col1:
        front_qty = st.number_input(
            "จำนวนนับ (หน้าร้าน)",
            min_value=0,
            step=1,
            value=existing["front_qty"] if existing else None,
            placeholder="ยังไม่ได้นับ",
            key=f"front_qty_{item_key}",
        )
    with col2:
        warehouse_qty = st.number_input(
            "จำนวนนับ (โกดัง)",
            min_value=0,
            step=1,
            value=existing["warehouse_qty"] if existing else None,
            placeholder="ยังไม่ได้นับ",
            key=f"warehouse_qty_{item_key}",
        )

    not_ready = front_qty is None and warehouse_qty is None
    if st.button(
        "💾 บันทึกจำนวนนับ", width="stretch", type="primary", disabled=not_ready
    ):
        try:
            append_count(
                user=user["name"],
                barcode=st.session_state.scanned_barcode,
                product_code=selected_row[product_code_col],
                name=selected_row[name_col],
                unit=selected_row[unit_col],
                lot=selected_row[lot_col],
                expiry=str(selected_row[expiry_col]),
                front_qty=front_qty,
                warehouse_qty=warehouse_qty,
            )
            st.success("บันทึกสำเร็จ")
            st.session_state.matches = None
            st.session_state.scanned_barcode = ""
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"บันทึกไม่สำเร็จ: {e}")
    if not_ready:
        st.caption("กรุณากรอกจำนวนนับอย่างน้อย 1 ช่องก่อนบันทึก")

st.divider()
st.subheader("ประวัติการนับล่าสุด")
try:
    recent = load_recent_counts()
    if recent.empty:
        st.caption("ยังไม่มีข้อมูล")
    else:
        st.dataframe(recent, width="stretch", hide_index=True)
except SheetNotConfiguredError:
    pass
except Exception as e:  # noqa: BLE001
    st.caption(f"โหลดประวัติไม่สำเร็จ: {e}")
