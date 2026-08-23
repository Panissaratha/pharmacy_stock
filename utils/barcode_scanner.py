from __future__ import annotations

from collections.abc import Callable

import streamlit as st

# โหลดไลบรารีอ่านบาร์โค้ดจากกล้อง (html5-qrcode รองรับทั้ง QR และบาร์โค้ด 1 มิติ
# เช่น EAN-13 ที่ใช้บนกล่องยาทั่วไป) ผ่าน CDN แบบไดนามิก
_HTML5_QRCODE_CDN_URL = "https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"

_HTML = """
<style>
  /* จำลองสไตล์ปุ่มมาตรฐานของ Streamlit (secondary button) ด้วยตัวแปรธีม --st-*
     เพื่อให้หน้าตาตรงกับปุ่ม "ค้นหา" ทั้งขนาด ขอบมน และสีตามธีมปัจจุบัน */
  .ph-scan-btn {
    display: block;
    width: 100%;
    box-sizing: border-box;
    margin-top: 0.5rem;
    padding: 0.375rem 0.75rem;
    min-height: 2.5rem;
    border-radius: var(--st-button-radius, 0.5rem);
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    background: var(--st-background-color, #ffffff);
    color: var(--st-text-color, #31333f);
    font-family: var(--st-font, inherit);
    font-size: var(--st-base-font-size, 1rem);
    font-weight: var(--st-base-font-weight, 400);
    line-height: 1.6;
    cursor: pointer;
  }
  .ph-scan-btn:hover {
    border-color: var(--st-primary-color, #ff4b4b);
    color: var(--st-primary-color, #ff4b4b);
  }
  .ph-scan-btn-open {
    background: #fff3cd;
  }
  .ph-scan-btn-open:hover {
    background: #ffecb0;
  }
</style>
<div>
  <button id="ph-scan-open" type="button" class="ph-scan-btn ph-scan-btn-open">📷 เปิดกล้องสแกนบาร์โค้ด</button>
  <button id="ph-scan-close" type="button" class="ph-scan-btn" style="display:none;">✕ ปิดกล้อง</button>
  <div id="ph-scan-status" style="font-size:0.85em;margin-top:6px;color:var(--st-text-color, #666);"></div>
  <div id="ph-scan-reader" style="width:100%;max-width:360px;margin-top:8px;display:none;"></div>
</div>
"""

# หมายเหตุ: ต้อง isolate_styles=False เพราะไลบรารี html5-qrcode ค้นหา element ด้วย
# document.getElementById() ซึ่งมองไม่เห็น element ที่อยู่ใน shadow root
_JS_TEMPLATE = """
export default function (component) {
  const { parentElement, setTriggerValue } = component

  const openBtn = parentElement.querySelector('#ph-scan-open')
  const closeBtn = parentElement.querySelector('#ph-scan-close')
  const readerEl = parentElement.querySelector('#ph-scan-reader')
  const statusEl = parentElement.querySelector('#ph-scan-status')
  if (!openBtn || !closeBtn || !readerEl || !statusEl) return

  let scanner = null

  function loadLibrary() {
    if (window.Html5Qrcode) return Promise.resolve()
    if (!window.__phHtml5QrcodeLoading) {
      window.__phHtml5QrcodeLoading = new Promise((resolve, reject) => {
        const script = document.createElement('script')
        script.src = '__CDN_URL__'
        script.onload = () => resolve()
        script.onerror = () => reject(new Error('load failed'))
        document.head.appendChild(script)
      })
    }
    return window.__phHtml5QrcodeLoading
  }

  async function stopScan() {
    if (scanner) {
      try {
        await scanner.stop()
        scanner.clear()
      } catch (e) {
        // กล้องอาจถูกปิดไปแล้ว ไม่ต้องทำอะไรเพิ่ม
      }
      scanner = null
    }
    readerEl.style.display = 'none'
    openBtn.style.display = 'block'
    closeBtn.style.display = 'none'
    statusEl.textContent = ''
  }

  async function startScan() {
    statusEl.textContent = 'กำลังโหลดตัวอ่านบาร์โค้ด...'
    try {
      await loadLibrary()
    } catch (e) {
      statusEl.textContent = 'โหลดตัวอ่านบาร์โค้ดไม่สำเร็จ ตรวจสอบอินเทอร์เน็ต'
      return
    }

    openBtn.style.display = 'none'
    closeBtn.style.display = 'block'
    readerEl.style.display = 'block'
    statusEl.textContent = 'กำลังเปิดกล้อง...'

    const formats = window.Html5QrcodeSupportedFormats
    scanner = new window.Html5Qrcode('ph-scan-reader', {
      formatsToSupport: [
        formats.EAN_13, formats.EAN_8, formats.UPC_A, formats.UPC_E,
        formats.CODE_128, formats.CODE_39, formats.CODABAR, formats.ITF,
      ],
      verbose: false,
    })

    try {
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 260, height: 160 } },
        (decodedText) => {
          setTriggerValue('scanned', decodedText)
          stopScan()
        },
        () => {}
      )
      statusEl.textContent = 'เล็งกล้องไปที่บาร์โค้ด'
    } catch (e) {
      statusEl.textContent = 'เปิดกล้องไม่สำเร็จ กรุณาอนุญาตให้เว็บนี้ใช้กล้อง'
      await stopScan()
    }
  }

  openBtn.onclick = startScan
  closeBtn.onclick = stopScan

  return () => { stopScan() }
}
"""

_JS = _JS_TEMPLATE.replace("__CDN_URL__", _HTML5_QRCODE_CDN_URL)

_COMPONENT = st.components.v2.component(
    "pharmacy_barcode_camera_scanner",
    html=_HTML,
    js=_JS,
    isolate_styles=False,
)


def barcode_camera_scanner(
    *,
    key: str,
    on_scanned_change: Callable[[], None] | None = None,
):
    if on_scanned_change is None:
        on_scanned_change = lambda: None  # noqa: E731
    return _COMPONENT(key=key, on_scanned_change=on_scanned_change)
