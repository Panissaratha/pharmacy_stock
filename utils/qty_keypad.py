from __future__ import annotations

import streamlit as st

# วิดเจ็ตกรอกจำนวนนับแบบมีปุ่มกดตัวเลขในหน้าเว็บเอง (ไม่พึ่งคีย์บอร์ดของระบบปฏิบัติการ)
#
# เหตุผล: เมื่อโทรศัพท์เชื่อมต่อกับเครื่องสแกนบาร์โค้ดผ่าน Bluetooth (ซึ่งเครื่องสแกน
# ทำตัวเป็นคีย์บอร์ด Bluetooth ให้ระบบปฏิบัติการ) ทั้ง Android และ iOS จะซ่อนคีย์บอร์ด
# บนหน้าจอไปเองโดยอัตโนมัติทุกครั้งที่แตะช่องกรอกข้อความ/ตัวเลข เพราะระบบคิดว่ามี
# คีย์บอร์ดจริงต่ออยู่แล้ว — พฤติกรรมนี้ถูกกำหนดโดยระบบปฏิบัติการเอง ไม่มีทางบังคับ
# ให้คีย์บอร์ดบนจอโผล่ขึ้นมาด้วย JavaScript ธรรมดาได้ (การ .focus() ช่องกรอกไม่ช่วย)
# ทางแก้ที่ทำงานได้แน่นอนทุกอุปกรณ์คือเลี่ยงไม่ใช้คีย์บอร์ดของระบบปฏิบัติการเลย
# แล้วสร้างปุ่มตัวเลข 0-9 ขึ้นมาเองในหน้าเว็บแทน

_HTML = """
<style>
  .qk-wrap { width: 100%; }
  .qk-label {
    font-size: 0.875rem;
    color: var(--st-text-color, #31333f);
    margin-bottom: 0.25rem;
  }
  .qk-display {
    display: block;
    width: 100%;
    box-sizing: border-box;
    text-align: left;
    padding: 0.375rem 0.75rem;
    min-height: 2.5rem;
    border-radius: var(--st-button-radius, 0.5rem);
    border: 1px solid var(--st-widget-border-color, rgba(49, 51, 63, 0.2));
    background: var(--st-background-color, #ffffff);
    color: var(--st-text-color, #31333f);
    font-family: var(--st-font, inherit);
    font-size: var(--st-base-font-size, 1rem);
    cursor: pointer;
  }
  .qk-display.qk-placeholder { color: var(--st-gray-color, #808495); }
  .qk-keypad {
    display: none;
    margin-top: 0.5rem;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-base-radius, 0.5rem);
    padding: 0.5rem;
    background: var(--st-secondary-background-color, #f0f2f6);
  }
  .qk-keypad.qk-open { display: block; }
  .qk-row { display: flex; gap: 0.4rem; margin-bottom: 0.4rem; }
  .qk-row:last-child { margin-bottom: 0; }
  .qk-key {
    flex: 1;
    padding: 0.6rem 0;
    font-size: 1.1rem;
    font-family: var(--st-font, inherit);
    border-radius: var(--st-button-radius, 0.5rem);
    border: 1px solid var(--st-widget-border-color, rgba(49, 51, 63, 0.2));
    background: var(--st-background-color, #ffffff);
    color: var(--st-text-color, #31333f);
    cursor: pointer;
  }
  .qk-key:active { background: var(--st-secondary-background-color, #f0f2f6); }
  .qk-key-done {
    flex: 1;
    background: var(--st-primary-color, #ff4b4b);
    color: #ffffff;
    border: none;
    font-weight: 600;
  }
</style>
<div class="qk-wrap">
  <div class="qk-label"></div>
  <button type="button" class="qk-display" id="qk-display"><span id="qk-value"></span></button>
  <div class="qk-keypad" id="qk-keypad">
    <div class="qk-row">
      <button type="button" class="qk-key" data-d="1">1</button>
      <button type="button" class="qk-key" data-d="2">2</button>
      <button type="button" class="qk-key" data-d="3">3</button>
    </div>
    <div class="qk-row">
      <button type="button" class="qk-key" data-d="4">4</button>
      <button type="button" class="qk-key" data-d="5">5</button>
      <button type="button" class="qk-key" data-d="6">6</button>
    </div>
    <div class="qk-row">
      <button type="button" class="qk-key" data-d="7">7</button>
      <button type="button" class="qk-key" data-d="8">8</button>
      <button type="button" class="qk-key" data-d="9">9</button>
    </div>
    <div class="qk-row">
      <button type="button" class="qk-key" id="qk-clear">ล้าง</button>
      <button type="button" class="qk-key" data-d="0">0</button>
      <button type="button" class="qk-key" id="qk-back">⌫</button>
    </div>
    <div class="qk-row">
      <button type="button" class="qk-key qk-key-done" id="qk-done">✓ เสร็จสิ้น</button>
    </div>
  </div>
</div>
"""

_JS = """
export default function (component) {
  const { parentElement, data, setStateValue } = component

  const labelEl = parentElement.querySelector(".qk-label")
  const displayBtn = parentElement.querySelector("#qk-display")
  const valueEl = parentElement.querySelector("#qk-value")
  const keypad = parentElement.querySelector("#qk-keypad")
  if (!labelEl || !displayBtn || !valueEl || !keypad) return

  labelEl.textContent = data?.label ?? ""

  let buffer = (data && typeof data.value === "string") ? data.value : ""
  let isOpen = !!(data && data.open)

  function render() {
    if (buffer === "") {
      valueEl.textContent = data?.placeholder ?? "ยังไม่ได้นับ"
      displayBtn.classList.add("qk-placeholder")
    } else {
      valueEl.textContent = buffer
      displayBtn.classList.remove("qk-placeholder")
    }
    if (isOpen) keypad.classList.add("qk-open")
    else keypad.classList.remove("qk-open")
  }
  render()

  function setOpen(next) {
    isOpen = next
    setStateValue("open", next)
    render()
  }

  // ทุกครั้งที่กดปุ่มตัวเลข/ล้าง/ลบ ต้องส่งค่า "open: true" กำกับไปด้วยเสมอ ไม่ใช่
  // แค่ตอนเปิด/ปิดเท่านั้น เพราะแต่ละครั้งที่ setStateValue ทำให้ Streamlit rerun
  // สคริปต์ทั้งหน้าใหม่ ถ้าไม่ยืนยันสถานะเปิดซ้ำทุกครั้ง คีย์บอร์ดจะปิดตัวเองไปหลัง
  // กดตัวเลขตัวแรกเสมอ ทำให้ต้องแตะเปิดใหม่ก่อนกดตัวเลขตัวถัดไปทุกครั้ง
  function setValueStayOpen(nextBuffer) {
    buffer = nextBuffer
    isOpen = true
    setStateValue("value", buffer)
    setStateValue("open", true)
    render()
  }

  displayBtn.onclick = () => setOpen(!isOpen)

  parentElement.querySelectorAll(".qk-key[data-d]").forEach((btn) => {
    btn.onclick = () => {
      const d = btn.getAttribute("data-d")
      if (buffer.length >= 6) return
      setValueStayOpen(buffer === "0" ? d : buffer + d)
    }
  })

  const clearBtn = parentElement.querySelector("#qk-clear")
  if (clearBtn) {
    clearBtn.onclick = () => setValueStayOpen("")
  }

  const backBtn = parentElement.querySelector("#qk-back")
  if (backBtn) {
    backBtn.onclick = () => setValueStayOpen(buffer.slice(0, -1))
  }

  const doneBtn = parentElement.querySelector("#qk-done")
  if (doneBtn) {
    doneBtn.onclick = () => setOpen(false)
  }

  if (data && data.autoOpen && !isOpen) {
    setOpen(true)
  }
}
"""

_QTY_KEYPAD = st.components.v2.component(
    "pharmacy_qty_keypad",
    html=_HTML,
    js=_JS,
)


def qty_keypad(
    *,
    label: str,
    key: str,
    initial_value: int | None,
    auto_open: bool = False,
) -> int | None:
    """ช่องกรอกจำนวนนับแบบมีปุ่มกดตัวเลขในตัว คืนค่า int หรือ None ถ้ายังไม่ได้กรอก"""
    # คีย์ของ bidi component ห้ามมี "__" (สงวนไว้เป็นตัวคั่นภายในของ Streamlit) แต่
    # item_key ของแอปใช้ "__" คั่นบาร์โค้ด/ล็อต/วันหมดอายุ จึงต้องแทนที่ก่อนใช้เป็นคีย์
    key = key.replace("__", "-")
    component_state = st.session_state.get(key, {})
    value = component_state.get(
        "value", str(initial_value) if initial_value is not None else ""
    )
    open_state = component_state.get("open", auto_open)
    result = _QTY_KEYPAD(
        key=key,
        data={
            "label": label,
            "value": value,
            "open": open_state,
            "placeholder": "ยังไม่ได้นับ",
        },
        on_value_change=lambda: None,
        on_open_change=lambda: None,
    )
    value_str = result.value if result.value is not None else value
    if value_str in (None, ""):
        return None
    try:
        return int(value_str)
    except ValueError:
        return None
