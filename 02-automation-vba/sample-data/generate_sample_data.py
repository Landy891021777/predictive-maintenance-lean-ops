"""
把 VAE 模型的判讀結果，包裝成模擬「每日 SAP 匯出檔」（含刻意的髒資料）。

=== 這一步在整條資料流的位置 ===
    01-core-model/scoring/score_engines.py
        -> outputs/model_predictions.csv      （系統每日輸出：逐筆讀數的模型判讀）
              |  本腳本
        -> sample-data/<mode>/SAP_EXPORT_*.csv （模擬從 SAP 匯出的髒檔案）
              |  [VBA] CleanAndSummarize
        -> 依機台彙總的警告報表

=== 兩種切法（mode）===
lifecycle（預設主力，已用於實測計時）
    把每台引擎的完整生命週期，依 cycle 排序後平均切成 3 段，分配到 3 個匯出日。
    每個匯出檔含全部 100 台；因每台後段更接近故障，Warning 隨匯出日明顯遞增。
    語意：「累積的歷史讀數，分批下載」。資料量大（約 13,750 列），適合講退化趨勢與 ROI。

snapshot（艦隊快照）
    每台引擎只取最後 3 個 cycle，day1=N-2, day2=N-1, day3=N。
    每個匯出檔 = 100 台各回報「當下這一刻」的一筆讀數（共 300 列 + 重複）。
    語意：「每天全艦隊各回報一筆當前狀態」。最貼近真實每日匯出；
    因連續三個 cycle 健康幾乎不變，Warning 大致持平（回答「現在誰該修」而非「怎麼退化」）。

=== 資料誠信說明 ===
真實（來自 NASA CMAPSS test_FD001 + VAE 模型）：
    EquipmentID / Cycle / Sensor_*（12 欄）/ LatentZ1 / LatentZ2 /
    NearestDistance / PredictedStatus（模型判讀 Healthy/Warning）
模擬（SAP/ERP 側欄位，CMAPSS 不含）：
    ExportDate / Timestamp / WorkOrder / MaintenanceCost
**不含任何來自 RUL_FD001 的真實答案**（現實中故障尚未發生，系統不會知道答案）。

刻意加入的髒資料：EquipmentID 前後空白(15%)/小寫(10%)、PredictedStatus 大小寫不一(15%)、
    ExportDate 三種格式、MaintenanceCost 千分位+缺值(7%)、NearestDistance 缺值(3%)、重複列(5%)。

執行：
    py -3 generate_sample_data.py            # 兩種都產生（預設）
    py -3 generate_sample_data.py lifecycle  # 只產生 lifecycle
    py -3 generate_sample_data.py snapshot   # 只產生 snapshot
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
PRED_FILE = OUT_DIR.parent.parent / "01-core-model" / "outputs" / "model_predictions.csv"

KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
N_EXPORT_DAYS = 3
BASE_TS = datetime(2026, 1, 1)
BASE_EXPORT_DAY = datetime(2026, 7, 1)

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
        return f"  {eid} "
    if r < 0.25:
        return eid.lower()
    return eid


def dirty_date(d: datetime) -> str:
    return d.strftime(random.choice(["%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d"]))


def dirty_status(status: str) -> str:
    r = random.random()
    if r < 0.10:
        return status.lower()
    if r < 0.15:
        return status.upper()
    return status


def dirty_cost(is_warning: bool) -> str:
    if random.random() < 0.07:
        return ""
    value = random.uniform(800, 25000) if is_warning else random.uniform(50, 3000)
    return f"{value:,.2f}" if random.random() < 0.4 else f"{value:.2f}"


def dirty_distance(d: float) -> str:
    return "" if random.random() < 0.03 else f"{d:.6f}"


# ---------- 切法（mode）----------

def assign_days_lifecycle(df: pd.DataFrame) -> pd.DataFrame:
    """每台引擎的完整生命週期依 cycle 排序，平均切成 3 段。"""
    df = df.sort_values(["unit_number", "time_cycles"]).copy()
    days = []
    for _, grp in df.groupby("unit_number", sort=False):
        n = len(grp)
        days.extend(min(i * N_EXPORT_DAYS // n, N_EXPORT_DAYS - 1) for i in range(n))
    df["day"] = days
    return df


def assign_days_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """每台引擎只取最後 3 個 cycle：day1=N-2, day2=N-1, day3=N。"""
    df = df.sort_values(["unit_number", "time_cycles"]).copy()
    keep = []
    for _, grp in df.groupby("unit_number", sort=False):
        last3 = grp.tail(N_EXPORT_DAYS).copy()
        last3["day"] = range(N_EXPORT_DAYS - len(last3), N_EXPORT_DAYS)
        keep.append(last3)
    return pd.concat(keep, ignore_index=True)


# ---------- 組裝 ----------

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


def build_file(chunk: pd.DataFrame, export_day: datetime, out_dir: Path):
    rows = [to_row(r, export_day) for r in chunk.itertuples(index=False)]
    units = chunk["unit_number"].nunique()
    warnings = int((chunk["PredictedStatus"] == "Warning").sum())

    n_dup = int(len(rows) * 0.05)
    rows.extend(list(random.choice(rows)) for _ in range(n_dup))
    random.shuffle(rows)

    path = out_dir / f"SAP_EXPORT_{export_day:%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    return path, len(rows), n_dup, units, warnings


def generate(mode: str, preds: pd.DataFrame) -> None:
    random.seed(42)  # 固定亂數：每個 mode 各自從相同種子開始，結果可重現
    out_dir = OUT_DIR / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("SAP_EXPORT_*.csv"):
        old.unlink()

    assign = assign_days_lifecycle if mode == "lifecycle" else assign_days_snapshot
    df = assign(preds)

    print(f"\n[{mode}] {len(df)} 列、{df['unit_number'].nunique()} 台引擎、"
          f"{(df['PredictedStatus'] == 'Warning').sum()} 筆 Warning")
    total_rows = total_dup = 0
    for d in range(N_EXPORT_DAYS):
        chunk = df[df["day"] == d]
        path, nrows, ndup, units, warns = build_file(
            chunk, BASE_EXPORT_DAY + timedelta(days=d), out_dir)
        total_rows += nrows
        total_dup += ndup
        print(f"  {mode}/{path.name}: {nrows} 列（{ndup} 重複）, {units} 台, {warns} 筆 Warning")
    print(f"  合計：{total_rows} 原始列 -> 去重後約 {total_rows - total_dup} 列")


def main() -> None:
    if not PRED_FILE.exists():
        raise FileNotFoundError(
            f"找不到模型結果表：{PRED_FILE}\n請先執行 01-core-model/scoring/score_engines.py")

    preds = pd.read_csv(PRED_FILE, encoding="utf-8-sig")
    print(f"讀入模型判讀結果：{len(preds)} 筆、{preds['unit_number'].nunique()} 台引擎")

    arg = sys.argv[1] if len(sys.argv) > 1 else "both"
    modes = ["lifecycle", "snapshot"] if arg == "both" else [arg]
    for m in modes:
        if m not in ("lifecycle", "snapshot"):
            raise SystemExit(f"未知 mode：{m}（可用 lifecycle / snapshot / both）")
        generate(m, preds)


if __name__ == "__main__":
    main()
