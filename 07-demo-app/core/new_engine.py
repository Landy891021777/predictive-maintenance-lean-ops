"""
導入新引擎：解析上傳檔、逐筆判讀、套用適用範圍檢查、彙總每台引擎。

=== 適用範圍檢查（見 build/export_new_engine_assets.py 的評估）===
模型以 FD001（單一運轉條件）訓練。讀數到最近 support 點的距離超過門檻時，
代表它不像模型見過的任何資料（常見原因：運轉條件不同，或已嚴重退化）：
  - 模型判 Warning → 保留 Warning
  - 模型判 Healthy → 改為 Unknown（無法確認），不宣告健康
理由：實測超出範圍時判 Warning 的 17 台全部真的快故障，判 Healthy 的 495 台中 163 台其實快故障。
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

SENSOR_COLS = [f"s_{i}" for i in range(1, 22)]
NASA_COLS = ["unit", "cycle", "setting_1", "setting_2", "setting_3"] + SENSOR_COLS

MAX_ROWS = 60_000
MAX_ENGINES = 300

WINDOW, L2_MIN, L3_MIN = 10, 3, 7       # 與《異常處置 SOP》相同

STATUS_LABEL = {"Healthy": "Healthy", "Warning": "Warning", "Unknown": "無法確認（超出適用範圍）"}


class UploadError(ValueError):
    """給使用者看的格式錯誤訊息。"""


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def _normalise_columns(cols: list[str]) -> dict[str, str]:
    """把常見的欄名寫法對應到 s_1…s_21 / unit / cycle。"""
    mapping = {}
    for c in cols:
        key = str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for prefix in ("sensor_", "s_", "sensor", "s"):
            if key.startswith(prefix) and key[len(prefix):].isdigit():
                n = int(key[len(prefix):])
                if 1 <= n <= 21:
                    mapping[c] = f"s_{n}"
                break
        if key in ("unit", "unit_number", "engine", "engine_id", "equipmentid", "id"):
            mapping[c] = "unit"
        if key in ("cycle", "cycles", "time_cycles", "time"):
            mapping[c] = "cycle"
    return mapping


def parse_upload(raw: bytes, filename: str = "") -> pd.DataFrame:
    """接受兩種格式：
    1. NASA CMAPSS 原始檔：空白分隔、無表頭、26 欄（unit, cycle, 3 個設定, 21 個感測器）
    2. 有表頭的 CSV：至少包含 21 個感測器欄（s_1…s_21 或 sensor_1…），unit / cycle 可省略
    """
    if not raw:
        raise UploadError("檔案是空的。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadError("無法以 UTF-8 讀取檔案，請確認是文字格式的 CSV 或 TXT。") from None

    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    tokens = first.replace(",", " ").replace(";", " ").split()
    looks_numeric = all(_is_number(t) for t in tokens)

    if looks_numeric and len(tokens) == 26:
        df = pd.read_csv(io.StringIO(text), sep=r"\s+", header=None, names=NASA_COLS)
    elif looks_numeric:
        raise UploadError(f"偵測到無表頭的數值檔，但每列有 {len(tokens)} 欄；NASA 原始格式應為 26 欄。")
    else:
        sep = ";" if first.count(";") > first.count(",") else ","
        df = pd.read_csv(io.StringIO(text), sep=sep)
        df = df.rename(columns=_normalise_columns(list(df.columns)))
        missing = [c for c in SENSOR_COLS if c not in df.columns]
        if missing:
            raise UploadError("缺少感測器欄位：" + "、".join(missing[:6]) + ("…" if len(missing) > 6 else "")
                              + "。需要 s_1 到 s_21 共 21 欄（也接受 sensor_1 這類寫法）。")
        if "unit" not in df.columns:
            df["unit"] = 1
        if "cycle" not in df.columns:
            df["cycle"] = df.groupby("unit").cumcount() + 1

    df = df[["unit", "cycle"] + SENSOR_COLS].copy()
    if len(df) == 0:
        raise UploadError("檔案中沒有資料列。")
    if len(df) > MAX_ROWS:
        raise UploadError(f"資料列太多（{len(df):,} 列），上限 {MAX_ROWS:,} 列。")

    for c in SENSOR_COLS + ["cycle"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = df[SENSOR_COLS + ["cycle"]].isna().any(axis=1)
    if bad.any():
        rows = "、".join(str(n) for n in (np.where(bad)[0][:5] + 2))
        raise UploadError(f"有 {int(bad.sum())} 列含非數值或空白（例如第 {rows} 列），請補齊後再上傳。")

    df["unit"] = df["unit"].astype(str).str.strip()
    if df["unit"].nunique() > MAX_ENGINES:
        raise UploadError(f"引擎數太多（{df['unit'].nunique()} 台），上限 {MAX_ENGINES} 台。")
    df["cycle"] = df["cycle"].astype(int)
    return df.sort_values(["unit", "cycle"], key=_natural_key).reset_index(drop=True)


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _natural_key(col: pd.Series) -> pd.Series:
    """unit 若是數字字串，依數值排序（2 排在 10 前面）。"""
    if col.name == "unit":
        num = pd.to_numeric(col, errors="coerce")
        return num if num.notna().all() else col
    return col


# ---------------------------------------------------------------------------
# 判讀
# ---------------------------------------------------------------------------

def guard(raw_status: np.ndarray, distance: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (套用檢查後的狀態, 是否在範圍內)。超出範圍的 Healthy → Unknown。"""
    in_range = distance <= threshold
    status = np.where(~in_range & (raw_status == "Healthy"), "Unknown", raw_status)
    return status, in_range


def assess_readings(detector, df: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """逐筆判讀。df 需含 unit、cycle 與 s_1…s_21。"""
    X = df[SENSOR_COLS].values.astype(np.float64)
    raw, _, dist = detector.classify_batch(X)
    status, in_range = guard(raw, dist, threshold)
    out = df[["unit", "cycle"]].copy()
    out["raw_status"] = raw
    out["status"] = status
    out["distance"] = dist
    out["in_range"] = in_range
    out["warning"] = (raw == "Warning").astype(int)
    out["recent_warnings"] = (out.groupby("unit")["warning"]
                              .transform(lambda x: x.rolling(WINDOW, min_periods=1).sum()))
    return out


def summarise_engines(readings: pd.DataFrame) -> pd.DataFrame:
    """每台引擎一列：最後狀態、SOP 等級、超出範圍比例。"""
    g = readings.groupby("unit", sort=False)
    last = g.tail(1).set_index("unit")
    ever_l3 = g["recent_warnings"].max() >= L3_MIN
    ever_l2 = g["recent_warnings"].max() >= L2_MIN
    level = np.select([ever_l3, ever_l2, g["warning"].max() > 0], ["L3 停機檢查", "L2 排程檢查", "L1 觀察"], "—")
    return pd.DataFrame({
        "unit": last.index,
        "readings": g.size().values,
        "last_cycle": last["cycle"].values,
        "last_status": last["status"].values,
        "last_raw_status": last["raw_status"].values,
        "last_distance": last["distance"].values,
        "out_of_range_share": (1 - g["in_range"].mean()).values,
        "warnings": g["warning"].sum().values,
        "sop_level": level,
    })
