"""
產生 Power BI 儀表板的乾淨資料源。

流程位置：
    02-automation-vba/sample-data/lifecycle/SAP_EXPORT_*.csv  （髒的 SAP 匯出）
        |  用與 VBA 巨集「相同的清理規則」（去重 / TRIM / 統一大小寫 / 千分位 / 日期）
        v
    05-powerbi-dashboard/data/fact_readings.csv               （乾淨事實表，Power BI 直接載入）

輸出應與 VBA 巨集一致：13,096 列、1,693 筆 Warning。

執行：py -3 prepare_powerbi_data.py
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "02-automation-vba" / "sample-data" / "lifecycle"
OUT_DIR = HERE / "data"

MONTHS = {m.upper(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]


def normalize_date(s: str) -> str:
    """統一三種日期格式為 yyyy-mm-dd（對應 VBA 的 NormalizeDate）。"""
    s = str(s).strip()
    if "/" in s:                                  # yyyy/mm/dd
        y, m, d = s.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    parts = s.split("-")
    if len(parts) == 3:
        if len(parts[0]) == 4:                    # yyyy-mm-dd
            y, m, d = parts
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        d, mon, y = parts                         # dd-Mon-yyyy
        return f"{int(y):04d}-{MONTHS[mon.upper()]:02d}-{int(d):02d}"
    return s


def clean_number(x) -> float | None:
    """去千分位逗號轉數值（對應 VBA 的 CleanNumber）；空值回 None。"""
    x = str(x).strip()
    if x == "" or x.lower() == "nan":
        return None
    return float(x.replace(",", ""))


def normalize_status(x: str) -> str:
    """統一大小寫（對應 VBA 的 NormalizeStatus）。"""
    u = str(x).strip().upper()
    if u == "WARNING":
        return "Warning"
    if u == "HEALTHY":
        return "Healthy"
    return str(x).strip()


def main() -> None:
    files = sorted(glob.glob(str(SRC / "SAP_EXPORT_*.csv")))
    if not files:
        raise FileNotFoundError(f"找不到 lifecycle 匯出檔：{SRC}")

    frames = [pd.read_csv(f, sep=";", encoding="utf-8-sig", dtype=str) for f in files]
    raw = pd.concat(frames, ignore_index=True)
    n_raw = len(raw)

    # --- 清理（與 VBA 巨集規則一致）---
    raw["EquipmentID"] = raw["EquipmentID"].str.strip().str.upper()
    raw["ExportDate"] = raw["ExportDate"].map(normalize_date)
    raw["PredictedStatus"] = raw["PredictedStatus"].map(normalize_status)
    raw["Cycle"] = raw["Cycle"].astype(int)

    # 去重鍵：日期 | 機台 | Cycle | 時戳 | 工單（對應 VBA 的 key）
    key = ["ExportDate", "EquipmentID", "Cycle", "Timestamp", "WorkOrder"]
    df = raw.drop_duplicates(subset=key).copy()
    n_dup = n_raw - len(df)

    # 數值欄位
    for s in SENSORS:
        df[f"Sensor_{s}"] = df[f"Sensor_{s}"].astype(float)
    df["LatentZ1"] = df["LatentZ1"].astype(float)
    df["LatentZ2"] = df["LatentZ2"].astype(float)
    df["NearestDistance"] = df["NearestDistance"].map(clean_number)
    df["MaintenanceCost"] = df["MaintenanceCost"].map(clean_number)
    df["IsWarning"] = (df["PredictedStatus"] == "Warning").astype(int)

    # 欄位順序整理
    cols = (["ExportDate", "EquipmentID", "Cycle", "Timestamp"]
            + [f"Sensor_{s}" for s in SENSORS]
            + ["LatentZ1", "LatentZ2", "NearestDistance",
               "PredictedStatus", "IsWarning", "WorkOrder", "MaintenanceCost"])
    df = df[cols].sort_values(["ExportDate", "EquipmentID", "Cycle"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "fact_readings.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")

    # 摘要
    warn = int(df["IsWarning"].sum())
    print(f"原始列：{n_raw}  去重移除：{n_dup}  乾淨列：{len(df)}")
    print(f"Warning 筆數：{warn}  （應為 1693）")
    print(f"機台數：{df['EquipmentID'].nunique()}  匯出日：{sorted(df['ExportDate'].unique())}")
    print(f"各匯出日 Warning：")
    print(df.groupby('ExportDate')['IsWarning'].sum().to_string())
    print(f"\n已輸出：{out}")


if __name__ == "__main__":
    main()
