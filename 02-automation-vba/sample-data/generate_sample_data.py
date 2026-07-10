"""
從真實的 NASA CMAPSS FD001 「測試集」產生模擬「SAP 匯出」的設備感測/工單檔（含刻意的髒資料）。

=== 為何用 test 集而非 train 集？ ===
train_FD001 中每台引擎都「跑到故障為止」，若以 RUL<=30 定義異常，
每台引擎必然剛好有 31 筆異常 —— 該欄位在儀表板上毫無比較價值。

test_FD001 的每台引擎是在故障前的隨機時間點被截斷，
搭配 RUL_FD001（各引擎在最後一個 cycle 的真實剩餘壽命），
正好對應真實情境：「當前艦隊快照 —— 100 台機台處在不同的壽命階段」。
少數逼近故障、多數健康，異常數自然分佈，儀表板才有預警價值。

RUL 計算（CMAPSS 標準做法）：
    該列 RUL = (該引擎在測試集的最大 cycle - 當前 cycle) + RUL_FD001[該引擎]

=== 資料誠信說明 ===
真實（來自 NASA CMAPSS test_FD001.txt + RUL_FD001.txt）：
  - EquipmentID   : 100 台引擎的真實 unit 編號（ENG-001 ~ ENG-100）
  - Cycle         : 真實運轉週期
  - Sensor_*      : 12 個關鍵感測器的真實量測值
                    （對齊本專案的特徵選擇：sensor 2,3,4,7,8,9,11,12,13,14,15,17）
  - HealthScore   : 由真實 RUL 推導 = min(RUL, 125) / 125
  - AnomalyFlag   : 由真實 RUL 判定 = 1 if RUL <= 30

模擬（CMAPSS 資料集不含這些欄位，它們屬於 SAP/ERP 側）：
  - ExportDate    : 每台引擎的 cycle 依時序切成 3 天批次匯出
                    （故每個匯出檔都含全部 100 台，且異常隨時間遞增）
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
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # 固定亂數，讓結果可重現

OUT_DIR = Path(__file__).parent
NASA_DIR = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
TEST_FILE = NASA_DIR / "test_FD001.txt"
RUL_FILE = NASA_DIR / "RUL_FD001.txt"

# CMAPSS 欄位：1=unit, 2=cycle, 3-5=op settings, 6-26=sensor_1..sensor_21
KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
SENSOR_COLS = {s: 5 + s for s in KEY_SENSORS}  # sensor_k 位於第 (5+k) 欄（1-indexed）

RUL_CAP = 125       # CMAPSS 文獻常用的分段線性 RUL 上限
ANOMALY_RUL = 30    # RUL <= 30 視為異常（早期預警窗）
N_EXPORT_DAYS = 3

HEADER = (
    ["ExportDate", "EquipmentID", "Cycle", "Timestamp"]
    + [f"Sensor_{s}" for s in KEY_SENSORS]
    + ["HealthScore", "AnomalyFlag", "WorkOrder", "MaintenanceCost"]
)

BASE_TS = datetime(2026, 1, 1)


# ---------- 讀取真實資料 ----------

def load_cmapss() -> list[dict]:
    for f in (TEST_FILE, RUL_FILE):
        if not f.exists():
            raise FileNotFoundError(f"找不到 CMAPSS 原始檔：{f}")

    # RUL_FD001 第 i 行 = 第 i 台引擎在最後一個 cycle 的真實剩餘壽命
    with RUL_FILE.open(encoding="utf-8") as f:
        rul_at_last = {i: int(line.split()[0]) for i, line in enumerate(f, start=1) if line.strip()}

    rows: list[dict] = []
    with TEST_FILE.open(encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 26:
                continue
            rows.append({
                "unit": int(parts[0]),
                "cycle": int(parts[1]),
                "sensors": {s: float(parts[SENSOR_COLS[s] - 1]) for s in KEY_SENSORS},
            })

    max_cycle: dict[int, int] = defaultdict(int)
    for r in rows:
        max_cycle[r["unit"]] = max(max_cycle[r["unit"]], r["cycle"])

    for r in rows:
        # CMAPSS 標準 RUL 推導
        rul = (max_cycle[r["unit"]] - r["cycle"]) + rul_at_last[r["unit"]]
        r["rul"] = rul
        r["health"] = min(rul, RUL_CAP) / RUL_CAP      # 真實退化 → 健康分數
        r["anomaly"] = 1 if rul <= ANOMALY_RUL else 0  # 真實退化 → 異常標記

    return rows


def assign_export_days(rows: list[dict]) -> None:
    """把每台引擎的 cycle 依時序切成 3 段，分配到 3 個匯出日。

    這確保：(1) 每個匯出檔都含全部 100 台引擎；
           (2) 異常隨匯出日遞增（真實退化趨勢）。
    """
    by_unit: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_unit[r["unit"]].append(r)

    for unit_rows in by_unit.values():
        unit_rows.sort(key=lambda r: r["cycle"])
        n = len(unit_rows)
        for i, r in enumerate(unit_rows):
            # 前 1/3 → day 0，中 1/3 → day 1，後 1/3 → day 2
            r["day"] = min(i * N_EXPORT_DAYS // n, N_EXPORT_DAYS - 1)


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


def build_file(records: list[dict], export_day: datetime) -> tuple[Path, int, int, int, int]:
    rows = [to_row(r, export_day) for r in records]
    units = len({r["unit"] for r in records})
    anomalies = sum(r["anomaly"] for r in records)

    # 製造髒資料：隨機複製約 5% 的列成為重複列
    n_dup = int(len(rows) * 0.05)
    rows.extend(list(random.choice(rows)) for _ in range(n_dup))
    random.shuffle(rows)

    path = OUT_DIR / f"SAP_EXPORT_{export_day:%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    return path, len(rows), n_dup, units, anomalies


def main() -> None:
    records = load_cmapss()
    assign_export_days(records)

    units = len({r["unit"] for r in records})
    print(f"讀入真實 CMAPSS 測試集：{len(records)} 列、{units} 台引擎、{len(KEY_SENSORS)} 個感測器")

    base = datetime(2026, 7, 1)
    total_rows = total_dup = 0
    for d in range(N_EXPORT_DAYS):
        chunk = [r for r in records if r["day"] == d]
        path, nrows, ndup, u, anom = build_file(chunk, base + timedelta(days=d))
        total_rows += nrows
        total_dup += ndup
        print(f"  {path.name}: {nrows} 列（{ndup} 重複）, {u} 台引擎, {anom} 筆異常")

    print(f"合計：{total_rows} 原始列 → 去重後應為 {total_rows - total_dup} 列")


if __name__ == "__main__":
    main()
