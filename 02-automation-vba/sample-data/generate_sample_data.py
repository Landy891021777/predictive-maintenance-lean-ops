"""
把 VAE 模型的判讀結果，包裝成模擬「每日 SAP 匯出檔」（含刻意的髒資料）。

=== 這一步在整條資料流的位置 ===
    01-core-model/scoring/score_engines.py
        → outputs/model_predictions.csv      （系統每日輸出：逐筆讀數的模型判讀）
              ↓  本腳本
        → sample-data/SAP_EXPORT_*.csv       （模擬從 SAP 匯出的髒檔案）
              ↓  [VBA] CleanAndSummarize
        → 依機台彙總的警告報表

=== 資料誠信說明 ===
真實（來自 NASA CMAPSS test_FD001 + 你的 VAE 模型）：
  - EquipmentID      : 100 台引擎的真實 unit 編號
  - Cycle            : 真實運轉週期
  - Sensor_*（12 欄）: 真實感測器量測值
  - LatentZ1 / LatentZ2 : VAE encoder 產生的真實 embedding 座標
  - NearestDistance  : 到最近 support set 點的真實距離
  - PredictedStatus  : 模型的真實判讀（Healthy / Warning）

模擬（SAP/ERP 側的欄位，CMAPSS 不含）：
  - ExportDate       : 每台引擎的 cycle 依時序切成 3 天批次匯出
  - Timestamp        : 由 Cycle 推導
  - WorkOrder        : 工單號
  - MaintenanceCost  : 維護成本（與判讀結果相關）

**本檔案不含任何來自 RUL_FD001 的真實答案。** 真實剩餘壽命只出現在
01-core-model/outputs/model_validation.csv，僅用於驗證模型準確率。
理由：現實中故障尚未發生，系統不可能知道引擎還剩幾個週期。

刻意加入的髒資料（模擬真實 SAP 匯出的品質問題）：
  - EquipmentID 前後空白（15%）、小寫（10%）
  - ExportDate 三種格式混用
  - PredictedStatus 大小寫不一致（15%）  ← 會讓人工樞紐把 Warning/warning 拆成兩類
  - MaintenanceCost 千分位逗號、缺值（7%）
  - NearestDistance 缺值（3%）
  - 重複列（每檔約 5%）

格式：分號(;)分隔 —— SAP 匯出常見格式，且可讓千分位逗號不破壞欄位。

執行：py -3 generate_sample_data.py
輸出：SAP_EXPORT_<日期>.csv  x 3
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)  # 固定亂數，讓結果可重現

OUT_DIR = Path(__file__).resolve().parent
PRED_FILE = OUT_DIR.parent.parent / "01-core-model" / "outputs" / "model_predictions.csv"

KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
N_EXPORT_DAYS = 3
BASE_TS = datetime(2026, 1, 1)

HEADER = (
    ["ExportDate", "EquipmentID", "Cycle", "Timestamp"]
    + [f"Sensor_{s}" for s in KEY_SENSORS]
    + ["LatentZ1", "LatentZ2", "NearestDistance", "PredictedStatus",
       "WorkOrder", "MaintenanceCost"]
)


# ---------- 髒資料製造器 ----------

def dirty_equipment_id(unit: int) -> str:
    eid = f"ENG-{unit:03d}"
    r = random.random()
    if r < 0.15:
        return f"  {eid} "     # 前後空白
    if r < 0.25:
        return eid.lower()     # 大小寫不一致
    return eid


def dirty_date(d: datetime) -> str:
    return d.strftime(random.choice(["%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d"]))


def dirty_status(status: str) -> str:
    r = random.random()
    if r < 0.10:
        return status.lower()   # warning / healthy
    if r < 0.15:
        return status.upper()   # WARNING / HEALTHY
    return status


def dirty_cost(is_warning: bool) -> str:
    if random.random() < 0.07:
        return ""                                       # 缺值
    value = random.uniform(800, 25000) if is_warning else random.uniform(50, 3000)
    if random.random() < 0.4:
        return f"{value:,.2f}"                          # 千分位 1,234.56
    return f"{value:.2f}"


def dirty_distance(d: float) -> str:
    return "" if random.random() < 0.03 else f"{d:.6f}"


# ---------- 組裝 ----------

def assign_export_days(df: pd.DataFrame) -> pd.DataFrame:
    """把每台引擎的 cycle 依時序切成 3 段，分配到 3 個匯出日。

    確保 (1) 每個匯出檔都含全部 100 台引擎；
        (2) 警告隨時間遞增（引擎單調退化）。
    """
    df = df.sort_values(["unit_number", "time_cycles"]).copy()
    days = []
    for _, grp in df.groupby("unit_number", sort=False):
        n = len(grp)
        days.extend(min(i * N_EXPORT_DAYS // n, N_EXPORT_DAYS - 1) for i in range(n))
    df["day"] = days
    return df


def to_row(r, export_day: datetime) -> list:
    ts = BASE_TS + timedelta(hours=int(r.time_cycles))
    is_warning = r.PredictedStatus == "Warning"
    return [
        dirty_date(export_day),
        dirty_equipment_id(int(r.unit_number)),
        int(r.time_cycles),
        ts.strftime("%Y-%m-%d %H:%M:%S"),
        *[f"{getattr(r, f'Sensor_{s}'):.4f}" for s in KEY_SENSORS],
        f"{r.LatentZ1:.6f}",
        f"{r.LatentZ2:.6f}",
        dirty_distance(r.NearestDistance),
        dirty_status(r.PredictedStatus),
        f"WO{random.randint(100000, 999999)}",
        dirty_cost(is_warning),
    ]


def build_file(chunk: pd.DataFrame, export_day: datetime):
    rows = [to_row(r, export_day) for r in chunk.itertuples(index=False)]
    units = chunk["unit_number"].nunique()
    warnings = int((chunk["PredictedStatus"] == "Warning").sum())

    n_dup = int(len(rows) * 0.05)
    rows.extend(list(random.choice(rows)) for _ in range(n_dup))
    random.shuffle(rows)

    path = OUT_DIR / f"SAP_EXPORT_{export_day:%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    return path, len(rows), n_dup, units, warnings


def main() -> None:
    if not PRED_FILE.exists():
        raise FileNotFoundError(
            f"找不到模型結果表：{PRED_FILE}\n"
            "請先執行 01-core-model/scoring/score_engines.py"
        )

    preds = pd.read_csv(PRED_FILE, encoding="utf-8-sig")
    preds = assign_export_days(preds)
    print(f"讀入模型判讀結果：{len(preds)} 筆、{preds['unit_number'].nunique()} 台引擎、"
          f"{(preds['PredictedStatus'] == 'Warning').sum()} 筆 Warning")

    base = datetime(2026, 7, 1)
    total_rows = total_dup = 0
    for d in range(N_EXPORT_DAYS):
        chunk = preds[preds["day"] == d]
        path, nrows, ndup, units, warns = build_file(chunk, base + timedelta(days=d))
        total_rows += nrows
        total_dup += ndup
        print(f"  {path.name}: {nrows} 列（{ndup} 重複）, {units} 台引擎, {warns} 筆 Warning")

    print(f"合計：{total_rows} 原始列 → 去重後應為 {total_rows - total_dup} 列")


if __name__ == "__main__":
    main()
