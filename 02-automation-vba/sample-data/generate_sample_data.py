"""
從真實的 NASA CMAPSS FD001 資料，產生模擬「SAP 匯出」的設備感測/工單檔（含刻意的髒資料）。

=== 資料誠信說明 ===
真實（來自 NASA CMAPSS train_FD001.txt）：
  - EquipmentID   : 100 台引擎的真實 unit 編號（ENG-001 ~ ENG-100）
  - Cycle         : 真實運轉週期
  - Sensor_*      : 12 個關鍵感測器的真實量測值
                    （對齊本專案的特徵選擇：sensor 2,3,4,7,8,9,11,12,13,14,15,17）
  - HealthScore   : 由真實 RUL（剩餘壽命）推導 = min(RUL, 125) / 125
  - AnomalyFlag   : 由真實退化判定 = 1 if RUL <= 30

模擬（CMAPSS 資料集不含這些欄位，它們屬於 SAP/ERP 側）：
  - ExportDate    : 假設分 3 天批次匯出
  - Timestamp     : 由 Cycle 推導的時間戳
  - WorkOrder     : 工單號
  - MaintenanceCost : 維護成本（與異常狀態相關）

刻意加入的髒資料（模擬真實 SAP 匯出的品質問題）：
  - EquipmentID 前後空白（15%）、小寫（10%）
  - ExportDate 三種格式混用
  - MaintenanceCost 千分位逗號、缺值（7%）
  - HealthScore 缺值（5%）
  - 重複列（每檔約 5%）

格式：分號(;)分隔 —— SAP 匯出常見格式，且可讓千分位逗號不破壞欄位。

執行：py -3 generate_sample_data.py
輸出：SAP_EXPORT_<日期>.csv  x 3
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # 固定亂數，讓結果可重現

OUT_DIR = Path(__file__).parent
CMAPSS_FILE = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案\train_FD001.txt")

# CMAPSS 欄位：1=unit, 2=cycle, 3-5=op settings, 6-26=sensor_1..sensor_21
# 本專案選用的 12 個關鍵感測器（見 01-core-model/docs/航太維修專案 背景.md）
KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
SENSOR_COLS = {s: 5 + s for s in KEY_SENSORS}  # sensor_k 位於第 (5+k) 欄（1-indexed）

RUL_CAP = 125       # CMAPSS 文獻常用的分段線性 RUL 上限
ANOMALY_RUL = 30    # RUL <= 30 視為異常（早期預警窗）

HEADER = (
    ["ExportDate", "EquipmentID", "Cycle", "Timestamp"]
    + [f"Sensor_{s}" for s in KEY_SENSORS]
    + ["HealthScore", "AnomalyFlag", "WorkOrder", "MaintenanceCost"]
)

BASE_TS = datetime(2026, 1, 1)


# ---------- 讀取真實資料 ----------

def load_cmapss() -> list[dict]:
    if not CMAPSS_FILE.exists():
        raise FileNotFoundError(
            f"找不到 CMAPSS 原始檔：{CMAPSS_FILE}\n"
            "請確認 kaggle 專案\\nasa專案\\train_FD001.txt 存在。"
        )

    rows: list[dict] = []
    with CMAPSS_FILE.open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 26:
                continue
            rows.append({
                "unit": int(parts[0]),
                "cycle": int(parts[1]),
                "sensors": {s: float(parts[SENSOR_COLS[s] - 1]) for s in KEY_SENSORS},
            })

    # 由真實資料計算 RUL：每台引擎的最大 cycle - 當前 cycle
    max_cycle: dict[int, int] = {}
    for r in rows:
        u = r["unit"]
        if r["cycle"] > max_cycle.get(u, 0):
            max_cycle[u] = r["cycle"]

    for r in rows:
        rul = max_cycle[r["unit"]] - r["cycle"]
        r["rul"] = rul
        r["health"] = min(rul, RUL_CAP) / RUL_CAP     # 真實退化 → 健康分數
        r["anomaly"] = 1 if rul <= ANOMALY_RUL else 0  # 真實退化 → 異常標記

    return rows


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


def dirty_cost(anomaly: int) -> str:
    if random.random() < 0.07:
        return ""                                       # 缺值
    value = random.uniform(800, 25000) if anomaly else random.uniform(50, 3000)
    if random.random() < 0.4:
        return f"{value:,.2f}"                          # 千分位 1,234.56
    return f"{value:.2f}"


def dirty_health(h: float) -> str:
    return "" if random.random() < 0.05 else f"{h:.4f}"


# ---------- 組裝輸出 ----------

def to_row(r: dict, export_day: datetime) -> list:
    ts = BASE_TS + timedelta(hours=r["cycle"])
    return [
        dirty_date(export_day),
        dirty_equipment_id(r["unit"]),
        r["cycle"],
        ts.strftime("%Y-%m-%d %H:%M:%S"),
        *[f"{r['sensors'][s]:.4f}" for s in KEY_SENSORS],
        dirty_health(r["health"]),
        r["anomaly"],
        f"WO{random.randint(100000, 999999)}",
        dirty_cost(r["anomaly"]),
    ]


def build_file(records: list[dict], export_day: datetime) -> tuple[Path, int, int]:
    rows = [to_row(r, export_day) for r in records]

    # 製造髒資料：隨機複製約 5% 的列成為重複列
    n_dup = int(len(rows) * 0.05)
    rows.extend(list(random.choice(rows)) for _ in range(n_dup))
    random.shuffle(rows)

    path = OUT_DIR / f"SAP_EXPORT_{export_day:%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    return path, len(rows), n_dup


def main() -> None:
    records = load_cmapss()
    units = len({r["unit"] for r in records})
    print(f"讀入真實 CMAPSS：{len(records)} 列、{units} 台引擎、{len(KEY_SENSORS)} 個感測器")

    # 依原始順序切成 3 批，模擬「每天一次批次匯出」
    n = len(records)
    bounds = [0, n // 3, 2 * n // 3, n]
    base = datetime(2026, 7, 1)

    total_rows = total_dup = 0
    for i in range(3):
        chunk = records[bounds[i]:bounds[i + 1]]
        path, nrows, ndup = build_file(chunk, base + timedelta(days=i))
        total_rows += nrows
        total_dup += ndup
        print(f"  {path.name}: {nrows} 列（其中 {ndup} 筆為重複列）")

    print(f"合計：{total_rows} 原始列 → 去重後應為 {total_rows - total_dup} 列")


if __name__ == "__main__":
    main()
