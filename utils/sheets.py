from __future__ import annotations

import datetime as dt

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ชื่อคอลัมน์ในชีตข้อมูลหลัก (MasterData) — แก้ให้ตรงกับหัวตารางจริงได้ที่นี่
MASTER_COLUMNS = {
    "barcode": "barcode",
    "product_code": "รหัสสินค้า",
    "name": "ชื่อยา",
    "unit": "หน่วยนับ",
    "lot": "เลขที่ล็อต",
    "expiry": "วันหมดอายุ",
}

LOG_COLUMNS = [
    "เวลาบันทึก",
    "ผู้บันทึก",
    "บาร์โค้ด",
    "รหัสสินค้า",
    "ชื่อยา",
    "หน่วยนับ",
    "เลขที่ล็อต",
    "วันหมดอายุ",
    "จำนวนหน้าร้าน",
    "จำนวนโกดัง",
    "ถูกเพิ่มใหม่",
]

NEW_LOT_FLAG = "ถูกเพิ่มใหม่"


class SheetNotConfiguredError(RuntimeError):
    pass


def _get_secret_section(name: str) -> dict:
    # st.secrets raises if no secrets.toml file exists at all (not just an
    # empty/missing key), so this must be guarded rather than using `in`/`.get`.
    try:
        return dict(st.secrets.get(name, {}))
    except Exception:
        return {}


@st.cache_resource(show_spinner=False)
def _get_client() -> gspread.Client:
    service_account_info = _get_secret_section("gcp_service_account")
    if not service_account_info:
        raise SheetNotConfiguredError(
            "ยังไม่ได้ตั้งค่า [gcp_service_account] ใน secrets.toml"
        )
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_spreadsheet():
    sheet_config = _get_secret_section("sheet")
    if "url" not in sheet_config:
        raise SheetNotConfiguredError("ยังไม่ได้ตั้งค่า [sheet].url ใน secrets.toml")
    client = _get_client()
    return client.open_by_url(sheet_config["url"])


def _master_worksheet_name() -> str:
    return _get_secret_section("sheet").get("master_worksheet", "MasterData")


def _log_worksheet_name() -> str:
    return _get_secret_section("sheet").get("log_worksheet", "CountLog")


def _get_all_records_as_str(ws) -> list[dict]:
    # gspread's get_all_records() numericises any column that "looks like a
    # number" based purely on the cell's string content — it ignores the
    # cell's declared number format entirely. That silently strips leading
    # zeros from codes like "003265" (int("003265") == 3265). Passing every
    # column index in numericise_ignore disables that conversion so codes
    # round-trip exactly as typed.
    headers = ws.row_values(1)
    numericise_ignore = list(range(1, len(headers) + 1))
    return ws.get_all_records(numericise_ignore=numericise_ignore)


@st.cache_data(ttl=60, show_spinner="กำลังโหลดข้อมูลยาจาก Google Sheet...")
def load_master_data() -> pd.DataFrame:
    ss = _get_spreadsheet()
    ws = ss.worksheet(_master_worksheet_name())
    records = _get_all_records_as_str(ws)
    df = pd.DataFrame(records)
    if not df.empty:
        # gspread auto-converts all-numeric cells (e.g. รหัสสินค้า, เลขที่ล็อต)
        # into numpy int64/float64, which isn't JSON-serializable when
        # writing back to the sheet later — force everything to plain str.
        df = df.astype(str)
        for col in df.columns:
            df[col] = df[col].str.strip()
    return df


def find_by_barcode(df: pd.DataFrame, barcode: str) -> pd.DataFrame:
    barcode = barcode.strip()
    col = MASTER_COLUMNS["barcode"]
    return df[df[col] == barcode]


def find_by_name(df: pd.DataFrame, name: str) -> pd.DataFrame:
    col = MASTER_COLUMNS["name"]
    return df[df[col] == name]


def list_drug_names(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    col = MASTER_COLUMNS["name"]
    return sorted(n for n in df[col].dropna().unique().tolist() if n)


def _ensure_log_worksheet(ss):
    name = _log_worksheet_name()
    try:
        ws = ss.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=1000, cols=len(LOG_COLUMNS))
        ws.append_row(LOG_COLUMNS)
    return ws


@st.cache_data(ttl=30, show_spinner=False)
def load_all_counts() -> pd.DataFrame:
    ss = _get_spreadsheet()
    ws = _ensure_log_worksheet(ss)
    records = _get_all_records_as_str(ws)
    return pd.DataFrame(records)


def _to_int_or_none(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def with_extra_lots(matches: pd.DataFrame) -> pd.DataFrame:
    """Union `matches` (drug rows found via barcode/name search) with any
    additional lots recorded in CountLog for the same barcode through the
    "เพิ่มล็อตใหม่" flow, so a newly-registered lot is selectable right away
    even though it isn't in MasterData yet."""
    lot_col = MASTER_COLUMNS["lot"]
    barcode_col = MASTER_COLUMNS["barcode"]
    if matches.empty:
        return matches

    barcode = str(matches.iloc[0][barcode_col]).strip()
    known_lots = set(matches[lot_col].astype(str).str.strip())
    try:
        counts_df = load_all_counts()
    except Exception:  # noqa: BLE001
        return matches
    if counts_df.empty:
        return matches

    rows = counts_df[counts_df["บาร์โค้ด"].astype(str).str.strip() == barcode]
    if rows.empty:
        return matches
    rows = rows.drop_duplicates(subset=["เลขที่ล็อต"], keep="last")
    rows = rows[~rows["เลขที่ล็อต"].astype(str).str.strip().isin(known_lots)]
    if rows.empty:
        return matches

    extra = pd.DataFrame(
        {
            MASTER_COLUMNS["barcode"]: rows["บาร์โค้ด"],
            MASTER_COLUMNS["product_code"]: rows["รหัสสินค้า"],
            MASTER_COLUMNS["name"]: rows["ชื่อยา"],
            MASTER_COLUMNS["unit"]: rows["หน่วยนับ"],
            MASTER_COLUMNS["lot"]: rows["เลขที่ล็อต"],
            MASTER_COLUMNS["expiry"]: rows["วันหมดอายุ"],
        }
    ).reset_index(drop=True)
    return pd.concat([matches, extra], ignore_index=True)


def _full_universe(master_df: pd.DataFrame, counts_df: pd.DataFrame) -> pd.DataFrame:
    """Every lot that should be tracked: MasterData plus any lot recorded in
    CountLog (e.g. via "เพิ่มล็อตใหม่") that isn't in MasterData yet."""
    barcode_col = MASTER_COLUMNS["barcode"]
    lot_col = MASTER_COLUMNS["lot"]
    if counts_df.empty:
        return master_df

    known = set()
    if not master_df.empty:
        known = set(
            zip(
                master_df[barcode_col].astype(str).str.strip(),
                master_df[lot_col].astype(str).str.strip(),
            )
        )

    counts_df = counts_df.copy()
    counts_df["_barcode"] = counts_df["บาร์โค้ด"].astype(str).str.strip()
    counts_df["_lot"] = counts_df["เลขที่ล็อต"].astype(str).str.strip()
    extra_rows = counts_df.drop_duplicates(subset=["_barcode", "_lot"], keep="last")
    extra_rows = extra_rows[
        ~extra_rows.apply(lambda r: (r["_barcode"], r["_lot"]) in known, axis=1)
    ]
    if extra_rows.empty:
        return master_df

    extra = pd.DataFrame(
        {
            MASTER_COLUMNS["barcode"]: extra_rows["บาร์โค้ด"],
            MASTER_COLUMNS["product_code"]: extra_rows["รหัสสินค้า"],
            MASTER_COLUMNS["name"]: extra_rows["ชื่อยา"],
            MASTER_COLUMNS["unit"]: extra_rows["หน่วยนับ"],
            MASTER_COLUMNS["lot"]: extra_rows["เลขที่ล็อต"],
            MASTER_COLUMNS["expiry"]: extra_rows["วันหมดอายุ"],
        }
    ).reset_index(drop=True)
    if master_df.empty:
        return extra
    return pd.concat([master_df, extra], ignore_index=True)


def _count_status_map(counts_df: pd.DataFrame) -> dict[tuple[str, str], dict]:
    status_map: dict[tuple[str, str], dict] = {}
    if counts_df.empty:
        return status_map
    for _, row in counts_df.iterrows():
        key = (str(row["บาร์โค้ด"]).strip(), str(row["เลขที่ล็อต"]).strip())
        status_map[key] = {
            "front_qty": _to_int_or_none(row["จำนวนหน้าร้าน"]),
            "warehouse_qty": _to_int_or_none(row["จำนวนโกดัง"]),
        }
    return status_map


def find_uncounted(
    master_df: pd.DataFrame, counts_df: pd.DataFrame, *, location: str = "both"
) -> pd.DataFrame:
    """Lots with no count recorded for the given location.

    location: "both" -> neither หน้าร้าน nor โกดัง has been counted
              "front" -> หน้าร้าน not counted (regardless of โกดัง)
              "warehouse" -> โกดัง not counted (regardless of หน้าร้าน)
    """
    universe = _full_universe(master_df, counts_df)
    if universe.empty:
        return universe

    barcode_col = MASTER_COLUMNS["barcode"]
    lot_col = MASTER_COLUMNS["lot"]
    status_map = _count_status_map(counts_df)

    def is_uncounted(row) -> bool:
        key = (str(row[barcode_col]).strip(), str(row[lot_col]).strip())
        status = status_map.get(key)
        front_done = status is not None and status["front_qty"] is not None
        warehouse_done = status is not None and status["warehouse_qty"] is not None
        if location == "front":
            return not front_done
        if location == "warehouse":
            return not warehouse_done
        return not front_done and not warehouse_done

    mask = universe.apply(is_uncounted, axis=1)
    return universe[mask]


def find_fully_counted(master_df: pd.DataFrame, counts_df: pd.DataFrame) -> pd.DataFrame:
    """Lots that have a recorded count at both หน้าร้าน and โกดัง."""
    universe = _full_universe(master_df, counts_df)
    if universe.empty:
        return universe

    barcode_col = MASTER_COLUMNS["barcode"]
    lot_col = MASTER_COLUMNS["lot"]
    status_map = _count_status_map(counts_df)

    def is_fully_counted(row) -> bool:
        key = (str(row[barcode_col]).strip(), str(row[lot_col]).strip())
        status = status_map.get(key)
        if status is None:
            return False
        return status["front_qty"] is not None and status["warehouse_qty"] is not None

    mask = universe.apply(is_fully_counted, axis=1)
    return universe[mask]


def find_latest_count(df: pd.DataFrame, barcode: str, lot: str) -> dict | None:
    if df.empty:
        return None
    matched = df[
        (df["บาร์โค้ด"].astype(str).str.strip() == barcode.strip())
        & (df["เลขที่ล็อต"].astype(str).str.strip() == str(lot).strip())
    ]
    if matched.empty:
        return None
    last = matched.iloc[-1]
    return {
        "front_qty": _to_int_or_none(last["จำนวนหน้าร้าน"]),
        "warehouse_qty": _to_int_or_none(last["จำนวนโกดัง"]),
    }


def _find_row_number(ws, barcode: str, lot: str) -> int | None:
    """Return the 1-based sheet row number of the last matching entry, if any."""
    records = _get_all_records_as_str(ws)
    row_number = None
    for i, record in enumerate(records):
        if (
            str(record.get("บาร์โค้ด", "")).strip() == barcode.strip()
            and str(record.get("เลขที่ล็อต", "")).strip() == str(lot).strip()
        ):
            row_number = i + 2  # +1 for the header row, +1 for 1-based indexing
    return row_number


def append_count(
    *,
    user: str,
    barcode: str,
    product_code: str,
    name: str,
    unit: str,
    lot: str,
    expiry: str,
    front_qty: float | None,
    warehouse_qty: float | None,
    is_new_lot: bool = False,
) -> None:
    ss = _get_spreadsheet()
    ws = _ensure_log_worksheet(ss)
    row = [
        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user,
        barcode,
        product_code,
        name,
        unit,
        lot,
        expiry,
        front_qty if front_qty is not None else "",
        warehouse_qty if warehouse_qty is not None else "",
        NEW_LOT_FLAG if is_new_lot else "",
    ]
    existing_row_number = _find_row_number(ws, barcode, lot)
    if existing_row_number is not None:
        ws.update(
            [row],
            range_name=f"A{existing_row_number}:K{existing_row_number}",
            value_input_option="USER_ENTERED",
        )
    else:
        ws.append_row(row, value_input_option="USER_ENTERED")
    load_recent_counts.clear()
    load_all_counts.clear()


@st.cache_data(ttl=30, show_spinner=False)
def load_recent_counts(limit: int = 20) -> pd.DataFrame:
    df = load_all_counts()
    if df.empty:
        return df
    return df.tail(limit).iloc[::-1].reset_index(drop=True)
