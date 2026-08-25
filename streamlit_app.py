from __future__ import annotations

import datetime as dt

import streamlit as st

from utils import auth
from utils.barcode_scanner import barcode_camera_scanner
from utils.sheets import (
    MASTER_COLUMNS,
    REMAINING_STOCK_VIEWERS,
    SheetNotConfiguredError,
    append_count,
    find_by_barcode,
    find_by_name,
    find_fully_counted,
    find_latest_count,
    find_uncounted,
    list_drug_names,
    load_all_counts,
    load_master_data,
    load_recent_counts,
    with_extra_lots,
)

st.set_page_config(
    page_title="นับสต็อก",
    page_icon="💊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

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

st.title("💊 นับสต็อก")

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

def _handle_camera_scan() -> None:
    result = st.session_state.get("camera_scanner")
    barcode = getattr(result, "scanned", None) if result is not None else None
    if not barcode:
        return
    try:
        df = load_master_data()
    except Exception:  # noqa: BLE001
        st.session_state.camera_scan_error = "โหลดข้อมูลยาไม่สำเร็จ กรุณาลองใหม่"
        return
    found = find_by_barcode(df, barcode)
    if found.empty:
        st.session_state.matches = None
        st.session_state.camera_scan_error = f"ไม่พบยาที่มีบาร์โค้ด: {barcode}"
    else:
        st.session_state.matches = found
        st.session_state.camera_scan_error = None
        st.session_state["barcode_field"] = barcode.strip()


def _handle_name_select() -> None:
    selected_name = st.session_state.get("name_search_select")
    if not selected_name:
        return
    try:
        df = load_master_data()
    except Exception:  # noqa: BLE001
        return
    found = find_by_name(df, selected_name)
    if not found.empty:
        st.session_state.matches = found


# ช่องสแกนบาร์โค้ด / ค้นหาด้วยชื่อยา / ปุ่มเปิดกล้อง อยู่ในกรอบเดียวกัน
with st.container(border=True):
    with st.form("barcode_form", clear_on_submit=True, border=False):
        barcode_input = st.text_input(
            "📷 สแกน หรือ กรอกเลขบาร์โค้ด", key="barcode_field"
        )
        scan_submit = st.form_submit_button("ค้นหา", width="stretch")

    if scan_submit and barcode_input.strip():
        matches = find_by_barcode(master_df, barcode_input)
        if matches.empty:
            st.error(f"ไม่พบยาที่มีบาร์โค้ด: {barcode_input}")
            st.session_state.matches = None
        else:
            st.session_state.matches = matches

    # st.selectbox กรอง option ให้เองแบบ live ตอนพิมพ์อยู่แล้ว (ในตัว widget เดียว)
    # จึงไม่ต้องมีช่องพิมพ์คำค้นหาแยกกับ dropdown แสดงผลอีกอัน
    name_options = list_drug_names(master_df)
    st.selectbox(
        "🔍 ค้นหาด้วยชื่อยา",
        options=name_options,
        index=None,
        placeholder="พิมพ์ชื่อยาบางส่วน..." if name_options else "ยังไม่มีข้อมูลยา",
        key="name_search_select",
        on_change=_handle_name_select,
        disabled=not name_options,
    )

    barcode_camera_scanner(key="camera_scanner", on_scanned_change=_handle_camera_scan)

if st.session_state.get("camera_scan_error"):
    st.error(st.session_state.camera_scan_error)
    st.session_state.camera_scan_error = None

# ให้เคอร์เซอร์กลับไปที่ช่องบาร์โค้ดอัตโนมัติ เพื่อสแกนชิ้นถัดไปได้ทันที
# ครอบด้วย IIFE เพราะสคริปต์นี้ถูกแทรกเข้า DOM ใหม่ทุกครั้งที่ rerun — ถ้าประกาศ
# const ไว้นอกฟังก์ชันจะชนกับตัวแปรเดิมจาก run ก่อนหน้าและโยน SyntaxError
st.html(
    """
    <script>
    (function () {
      const inputs = document.querySelectorAll('input[type="text"]');
      if (inputs.length > 0) { inputs[0].focus(); }
    })();
    </script>
    """,
    unsafe_allow_javascript=True,
)

# ทำให้ตัวเลือกล็อตที่นับไปแล้ว (หน้าร้าน/โกดัง/2 ที่) ในช่อง
# "เลือกเลขล็อต / วันหมดอายุ" ขึ้นสีฟ้า
# ตัวเลือก dropdown ของ Streamlit เป็น <div role="option"> ธรรมดา ไม่ใช่ <option>
# ของ native select จึงปรับสีได้ แต่ list จะถูกสร้างใหม่ทุกครั้งที่เปิด dropdown
# เลยต้องใช้ MutationObserver คอยจับแล้วค่อยใส่สี — ติดตั้ง observer แค่ครั้งเดียว
# (เช็คธงกันไว้) ไม่งั้นจะซ้อนกันหลาย observer ทุกรอบที่หน้าเว็บ rerun
st.html(
    """
    <script>
    (function () {
      if (window.__phLotOptionColorInstalled) return;
      window.__phLotOptionColorInstalled = true;

      const COUNTED_SUFFIXES = ['หน้าร้านนับแล้ว', 'โกดังนับแล้ว', 'นับ 2 ที่แล้ว'];

      function colorIfCounted(el) {
        if (
          el.getAttribute &&
          el.getAttribute('role') === 'option' &&
          el.innerText &&
          COUNTED_SUFFIXES.some((s) => el.innerText.includes(s))
        ) {
          el.style.color = '#0d6efd';
          el.style.fontWeight = '600';
        }
      }

      const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
          m.addedNodes.forEach((node) => {
            if (node.nodeType !== 1) return;
            colorIfCounted(node);
            if (node.querySelectorAll) {
              node.querySelectorAll('[role="option"]').forEach(colorIfCounted);
            }
          });
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });

      document.querySelectorAll('[role="option"]').forEach(colorIfCounted);
    })();
    </script>
    """,
    unsafe_allow_javascript=True,
)

# --- ขั้นตอนที่ 2: แสดงข้อมูลยา และกรอกจำนวนนับ ---
matches = st.session_state.matches
if matches is not None and not matches.empty:
    barcode_col = MASTER_COLUMNS["barcode"]
    product_code_col = MASTER_COLUMNS["product_code"]
    name_col = MASTER_COLUMNS["name"]
    unit_col = MASTER_COLUMNS["unit"]
    lot_col = MASTER_COLUMNS["lot"]
    expiry_col = MASTER_COLUMNS["expiry"]

    st.divider()

    # รวมล็อตที่เคย "เพิ่มล็อตใหม่" ไว้ใน CountLog เข้ากับล็อตจาก MasterData
    # เพื่อให้เลือกล็อตที่เพิ่มเองก่อนหน้านี้ได้จาก dropdown เดียวกันเลย
    matches = with_extra_lots(matches)

    st.subheader(f"ชื่อยา: {matches.iloc[0][name_col]}")
    st.write(f"หน่วยนับ: **{matches.iloc[0][unit_col]}**")

    if len(matches) > 1:
        st.error("มีหลายล็อต เลือกล็อตก่อนนับ")

        try:
            _counts_for_labels = load_all_counts()
        except Exception:  # noqa: BLE001
            _counts_for_labels = None

        def _lot_label(row) -> str:
            label = f"ล็อต {row[lot_col]} — หมดอายุ {row[expiry_col]}"
            if _counts_for_labels is None:
                return label
            try:
                status = find_latest_count(
                    _counts_for_labels,
                    str(row[barcode_col]),
                    str(row[lot_col]),
                    str(row[expiry_col]),
                )
            except Exception:  # noqa: BLE001
                status = None
            if status is None:
                return label
            front_done = status["front_qty"] is not None
            warehouse_done = status["warehouse_qty"] is not None
            if front_done and warehouse_done:
                suffix = "นับ 2 ที่แล้ว"
            elif front_done:
                suffix = "หน้าร้านนับแล้ว"
            elif warehouse_done:
                suffix = "โกดังนับแล้ว"
            else:
                return label
            return f"{label} - {suffix}"

        options = [_lot_label(row) for _, row in matches.iterrows()]
        selected = st.selectbox("เลือกเลขล็อต / วันหมดอายุ", options)
        selected_row = matches.iloc[options.index(selected)]
    else:
        st.info("มีล็อตเดียว")
        selected_row = matches.iloc[0]
        st.write(
            f"เลขที่ล็อต: **{selected_row[lot_col]}**  |  "
            f"วันหมดอายุ: **{selected_row[expiry_col]}**"
        )

    # ข้อมูลคงเหลือ/เกิน/ขาด เป็นข้อมูลรายล็อต (เทียบกับ CountLog ของล็อตนั้นๆ)
    # และให้เห็นเฉพาะ user ที่กำหนดไว้
    if user["username"] in REMAINING_STOCK_VIEWERS:
        remaining_col = MASTER_COLUMNS["remaining"]
        excess_col = MASTER_COLUMNS["excess"]
        shortfall_col = MASTER_COLUMNS["shortfall"]
        remaining_value = selected_row.get(remaining_col, "")
        excess_value = selected_row.get(excess_col, "")
        shortfall_value = selected_row.get(shortfall_col, "")
        st.write(
            f"คงเหลือ: **{remaining_value if remaining_value else '-'}**  |  "
            f"เกิน: **{excess_value if excess_value else '-'}**  |  "
            f"ขาด: **{shortfall_value if shortfall_value else '-'}**"
        )

    actual_barcode = str(selected_row[barcode_col])
    lot_value = str(selected_row[lot_col])
    expiry_value = str(selected_row[expiry_col])
    try:
        existing = find_latest_count(
            load_all_counts(), actual_barcode, lot_value, expiry_value
        )
    except Exception:  # noqa: BLE001
        existing = None

    if existing and (
        existing["front_qty"] is not None or existing["warehouse_qty"] is not None
    ):
        st.caption("เคยนับไปแล้ว — แก้ไขแล้วบันทึกซ้ำได้")

    # คีย์ของ widget ต้องผูกกับบาร์โค้ด+ล็อต เพื่อให้ค่าที่กรอกไม่ตกค้าง
    # ข้ามไปยังยาตัวถัดไปเมื่อสแกนรายการใหม่โดยยังไม่ได้บันทึก
    item_key = f"{actual_barcode}__{lot_value}__{expiry_value}"

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
                barcode=actual_barcode,
                product_code=selected_row[product_code_col],
                name=selected_row[name_col],
                unit=selected_row[unit_col],
                lot=selected_row[lot_col],
                expiry=str(selected_row[expiry_col]),
                front_qty=front_qty,
                warehouse_qty=warehouse_qty,
            )
            st.success("บันทึกสำเร็จ")
            # ถ้ายามีหลายล็อต ให้ค้างอยู่ที่ตัวเดิมเพื่อเลือกล็อตถัดไปจาก
            # dropdown ต่อได้เลย ไม่ต้องค้นหาชื่อยาใหม่อีกรอบ
            if len(matches) <= 1:
                st.session_state.matches = None
            st.session_state.pop("name_search_select", None)
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"บันทึกไม่สำเร็จ: {e}")
    if not_ready:
        st.caption("กรุณากรอกจำนวนนับอย่างน้อย 1 ช่องก่อนบันทึก")

    st.html(
        """
        <style>
        .st-key-new_lot_expander summary {
          background-color: #fff3cd;
        }
        .st-key-new_lot_expander summary:hover {
          background-color: #ffecb0;
        }
        </style>
        """
    )
    with st.expander(
        "➕ เพิ่มล็อตใหม่ (ถ้าไม่มีเลขล็อตนี้ในรายการ)", key="new_lot_expander"
    ):
        new_lot_key = f"new_lot_input_{actual_barcode}"
        new_expiry_key = f"new_expiry_input_{actual_barcode}"
        new_lot = st.text_input("เลขที่ล็อต", key=new_lot_key)
        new_expiry = st.date_input(
            "วันหมดอายุ",
            value=None,
            # ยาบางตัวอายุยาวหลายสิบปี ขยายเพดานให้กว้างกว่าค่าเริ่มต้น (~10 ปี) ของ Streamlit
            max_value=dt.date.today() + dt.timedelta(days=365 * 30),
            format="DD/MM/YYYY",
            key=new_expiry_key,
        )
        if st.button("บันทึกล็อตใหม่", key=f"save_new_lot_{actual_barcode}"):
            if not new_lot.strip() or new_expiry is None:
                st.error("กรุณากรอกเลขล็อตและวันหมดอายุให้ครบ")
            else:
                try:
                    append_count(
                        user=user["name"],
                        barcode=actual_barcode,
                        product_code=matches.iloc[0][product_code_col],
                        name=matches.iloc[0][name_col],
                        unit=matches.iloc[0][unit_col],
                        lot=new_lot.strip(),
                        expiry=new_expiry.strftime("%d/%m/%Y"),
                        front_qty=None,
                        warehouse_qty=None,
                        is_new_lot=True,
                    )
                    st.success("เพิ่มล็อตใหม่แล้ว เลือกได้จาก dropdown ด้านบน")
                    st.session_state.pop(new_lot_key, None)
                    st.session_state.pop(new_expiry_key, None)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"บันทึกไม่สำเร็จ: {e}")

st.divider()
with st.expander("🕘 ประวัติการนับล่าสุด"):
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


def _status_table(df) -> None:
    # ยาตัวเดียวกันอาจมีหลายล็อต บางล็อตนับแล้วบางล็อตยังไม่นับ และเลขล็อต
    # เดียวกันก็อาจมีคนละวันหมดอายุ (คนละล็อตทางกายภาพ) ต้องโชว์ทั้งเลขล็อต
    # และวันหมดอายุเสมอ ไม่งั้นจะดูเหมือนยาที่นับไปแล้วโผล่มาซ้ำ
    name_col = MASTER_COLUMNS["name"]
    unit_col = MASTER_COLUMNS["unit"]
    lot_col = MASTER_COLUMNS["lot"]
    expiry_col = MASTER_COLUMNS["expiry"]
    st.dataframe(
        df[[name_col, unit_col, lot_col, expiry_col]].reset_index(drop=True),
        width="stretch",
        hide_index=True,
    )


try:
    _counts_for_status = load_all_counts()

    with st.expander("📋 ยาที่ยังไม่ได้นับ"):

        def _uncounted_table(label: str, location: str) -> None:
            items = find_uncounted(master_df, _counts_for_status, location=location)
            st.caption(f"{label} ({len(items)} รายการ)")
            if items.empty:
                st.caption("ไม่มีรายการค้างนับ 🎉")
            else:
                _status_table(items)

        _uncounted_table("ยังไม่ได้นับทั้ง 2 ที่", "both")
        _uncounted_table("ยังไม่ได้นับหน้าร้าน", "front")
        _uncounted_table("ยังไม่ได้นับในโกดัง", "warehouse")

    with st.expander("✅ ยาที่นับเสร็จแล้วทั้ง 2 ที่"):
        completed = find_fully_counted(master_df, _counts_for_status)
        st.caption(f"{len(completed)} รายการ")
        if completed.empty:
            st.caption("ยังไม่มีรายการที่นับครบ")
        else:
            _status_table(completed)
except SheetNotConfiguredError:
    pass
except Exception as e:  # noqa: BLE001
    st.caption(f"โหลดสถานะการนับไม่สำเร็จ: {e}")
