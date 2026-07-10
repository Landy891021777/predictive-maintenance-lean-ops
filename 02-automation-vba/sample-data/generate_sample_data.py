"""
產生模擬「SAP 匯出」的設備感測/工單資料（含刻意的髒資料）。

用途：作為 02-automation-vba 的 VBA 清理巨集輸入，模擬維運工程師每天手動處理的檔案。
格式：分號(;)分隔的 CSV —— SAP 匯出常見格式，且可讓千分位逗號不破壞欄位。

執行：python generate_sample_data.py
輸出：SAP_EXPORT_<日期>.csv  x 3
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # 固定亂數，讓結果可重現

OUT_DIR = Path(__file__).parent
EQUIPMENT = ["ENG-001", "ENG-002", "ENG-003", "ENG-004", "ENG-005"]
SENSORS = ["Sensor_2", "Sensor_3", "Sensor_4", "Sensor_7", "Sensor_11"]

HEADER = [
    "ExportDate", "EquipmentID", "Timestamp",
    *SENSORS,
    "HealthScore", "AnomalyFlag", "WorkOrder", "MaintenanceCost",
]


def dirty_equipment_id(eid: str) -> str:
    """製造髒資料：前後空白、大小寫不一致。"""
    r = random.random()
    if r < 0.15:
        return f"  {eid} "
    if r < 0.25:
        return eid.lower()
    return eid


def dirty_date(d: datetime) -> str:
    """製造髒資料：三種不同日期格式混用。"""
    fmt = random.choice(["%Y/%m/%d", "%d-%b-%Y", "%Y-%m-%d"])
    return d.strftime(fmt)


def dirty_cost(value: float) -> str:
    """製造髒資料：千分位逗號、偶爾缺值。"""
    if random.random() < 0.07:
        return ""  # 缺值
    if random.random() < 0.4:
        return f"{value:,.2f}"  # 帶千分位 1,234.56
    return f"{value:.2f}"


def dirty_health(score: float) -> str:
    """製造髒資料：偶爾缺值。"""
    return "" if random.random() < 0.05 else f"{score:.3f}"


def make_row(export_day: datetime, ts: datetime) -> list:
    eid = random.choice(EQUIPMENT)
    # 健康分數 0~1，越低越接近故障
    health = max(0.0, min(1.0, random.gauss(0.72, 0.18)))
    anomaly = 1 if health < 0.45 else 0
    cost = random.uniform(800, 25000) if anomaly else random.uniform(50, 3000)

    return [
        dirty_date(export_day),
        dirty_equipment_id(eid),
        ts.strftime("%Y-%m-%d %H:%M:%S"),
        *[f"{random.gauss(500, 40):.3f}" for _ in SENSORS],
        dirty_health(health),
        anomaly,
        f"WO{random.randint(100000, 999999)}",
        dirty_cost(cost),
    ]


def build_file(export_day: datetime, n_rows: int = 200) -> Path:
    rows = []
    ts = datetime(export_day.year, export_day.month, export_day.day, 6, 0, 0)
    for _ in range(n_rows):
        rows.append(make_row(export_day, ts))
        ts += timedelta(minutes=random.randint(1, 5))

    # 製造髒資料：隨機複製約 5% 的列成為重複列
    for _ in range(int(n_rows * 0.05)):
        rows.append(list(random.choice(rows)))
    random.shuffle(rows)

    path = OUT_DIR / f"SAP_EXPORT_{export_day:%Y%m%d}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(HEADER)
        w.writerows(rows)
    return path


def main() -> None:
    base = datetime(2026, 7, 1)
    for i in range(3):
        p = build_file(base + timedelta(days=i))
        with p.open(encoding="utf-8-sig") as f:
            n = sum(1 for _ in f) - 1
        print(f"已產生 {p.name}（{n} 列，含重複/缺值/格式不一）")


if __name__ == "__main__":
    main()
