"""
02-automation-vba/src/CleanAndSummarize.bas 的逐規則 Python 重現。

為什麼要重現：雲端環境沒有 Windows / Excel，VBA 巨集與 Power Automate Desktop
都無法執行。這裡把同一套清理規則用 Python 寫一次，讓網頁上可以按鈕執行，
並由 build/verify_cleaning.py 對照 Power Automate 實際產出的報表
（03-rpa-power-automate/outbox/DailyHealthReport_20260711.xlsm）逐項驗證。

必須與 VBA 一致的細節（改之前先讀 .bas）：
  - 第一行是表頭，一律跳過；空白行不計數
  - 非空白行一律計入 rows_read，即使之後因欄位數不對或日期無法解析而被丟棄
  - 欄位數必須剛好 22，否則靜默丟棄
  - 日期無法解析的列靜默丟棄（不算重複、不進 clean）
  - EquipmentID = UCase(Trim(x))
  - status_fixed 只在「正規化後 ≠ 去空白後的原值」時 +1（純空白差異不算）
  - 缺值與 status_fixed 只統計「保留下來的列」，重複列不灌水
  - 去重鍵 = 日期(yyyy-mm-dd) | 機台 | Trim(Cycle) | Trim(Timestamp) | Trim(WorkOrder)
  - 數值用 VBA Val() 語意：只取開頭能解析的數字；成本先去千分位逗號
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

DELIM = ";"
COL_COUNT = 22

IX_DATE, IX_EQUIP, IX_CYCLE, IX_TS = 0, 1, 2, 3
IX_SENSOR_FIRST, IX_SENSOR_LAST = 4, 15
IX_Z1, IX_Z2, IX_DIST, IX_STATUS, IX_WO, IX_COST = 16, 17, 18, 19, 20, 21

COLUMNS = [
    "ExportDate", "EquipmentID", "Cycle", "Timestamp",
    "Sensor_2", "Sensor_3", "Sensor_4", "Sensor_7", "Sensor_8", "Sensor_9",
    "Sensor_11", "Sensor_12", "Sensor_13", "Sensor_14", "Sensor_15", "Sensor_17",
    "LatentZ1", "LatentZ2", "NearestDistance", "PredictedStatus",
    "WorkOrder", "MaintenanceCost",
]

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_VAL_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eEdD][+-]?\d+)?")


# ---------------------------------------------------------------------------
# VBA 內建函式的語意
# ---------------------------------------------------------------------------

def vba_val(s: str) -> float:
    """VBA Val()：忽略空白，只解析開頭的數字，解析不到回傳 0。"""
    t = re.sub(r"\s+", "", s)
    m = _VAL_RE.match(t)
    if not m:
        return 0.0
    return float(m.group(0).replace("d", "e").replace("D", "e"))


def normalize_status(s: str) -> str:
    u = s.strip().upper()
    if u == "WARNING":
        return "Warning"
    if u == "HEALTHY":
        return "Healthy"
    return s.strip()


def normalize_date(s: str) -> date | None:
    """三種混用格式：yyyy/mm/dd、yyyy-mm-dd、dd-Mon-yyyy。"""
    s = s.strip()
    try:
        if "/" in s:
            p = s.split("/")
            return date(int(p[0]), int(p[1]), int(p[2])) if len(p) == 3 else None
        if "-" in s:
            p = s.split("-")
            if len(p) != 3:
                return None
            if len(p[0]) == 4:
                return date(int(p[0]), int(p[1]), int(p[2]))
            mon = p[1].strip().upper()
            if mon in MONTHS:
                return date(int(p[2]), MONTHS.index(mon) + 1, int(p[0]))
    except ValueError:
        return None
    return None


def clean_number(s: str) -> float:
    return vba_val(s.strip().replace(",", ""))


# ---------------------------------------------------------------------------
# 管線
# ---------------------------------------------------------------------------

@dataclass
class RunLog:
    """對應 VBA Summary 分頁左上角的 run log。"""

    files_read: int = 0
    rows_read: int = 0
    duplicates_removed: int = 0
    clean_rows: int = 0
    status_normalized: int = 0
    total_warnings: int = 0
    missing_distance: int = 0
    missing_cost: int = 0
    elapsed_seconds: float = 0.0
    # 以下 VBA 沒有輸出，但同樣是被靜默丟棄的列，揭露出來比較誠實
    dropped_bad_columns: int = 0
    dropped_bad_date: int = 0


@dataclass
class PipelineResult:
    log: RunLog
    clean: pd.DataFrame
    summary: pd.DataFrame
    files: list[str] = field(default_factory=list)


def run_pipeline(folder: Path) -> PipelineResult:
    start = time.perf_counter()
    log = RunLog()
    seen: set[str] = set()
    records: list[list] = []

    # VBA 的 Dir() 在 NTFS 上依檔名排序回傳；順序會影響「重複列保留哪一筆」
    files = sorted(folder.glob("*.csv"))
    for path in files:
        log.files_read += 1
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            for i, line in enumerate(fh):
                line = line.rstrip("\r\n")
                if i == 0 or not line.strip():
                    continue
                log.rows_read += 1

                parts = line.split(DELIM)
                if len(parts) != COL_COUNT:
                    log.dropped_bad_columns += 1
                    continue

                export_date = normalize_date(parts[IX_DATE])
                if export_date is None:
                    log.dropped_bad_date += 1
                    continue

                equip = parts[IX_EQUIP].strip().upper()
                raw_status = parts[IX_STATUS].strip()
                status = normalize_status(raw_status)

                dist_txt = parts[IX_DIST].strip()
                cost_txt = parts[IX_COST].strip()
                dist = None if not dist_txt else vba_val(dist_txt)
                cost = None if not cost_txt else clean_number(cost_txt)

                key = "|".join([
                    export_date.isoformat(), equip,
                    parts[IX_CYCLE].strip(), parts[IX_TS].strip(), parts[IX_WO].strip(),
                ])
                if key in seen:
                    log.duplicates_removed += 1
                    continue
                seen.add(key)

                if status != raw_status:
                    log.status_normalized += 1
                if dist is None:
                    log.missing_distance += 1
                if cost is None:
                    log.missing_cost += 1

                rec = [export_date, equip, int(vba_val(parts[IX_CYCLE])), parts[IX_TS].strip()]
                rec += [vba_val(parts[j].strip()) for j in range(IX_SENSOR_FIRST, IX_SENSOR_LAST + 1)]
                rec += [vba_val(parts[IX_Z1].strip()), vba_val(parts[IX_Z2].strip()),
                        dist, status, parts[IX_WO].strip(), cost]
                records.append(rec)

    clean = pd.DataFrame(records, columns=COLUMNS)
    summary = _summarise(clean)

    log.clean_rows = len(clean)
    log.total_warnings = int(summary["Warnings"].sum()) if len(summary) else 0
    log.elapsed_seconds = time.perf_counter() - start

    return PipelineResult(log=log, clean=clean, summary=summary,
                          files=[p.name for p in files])


def _summarise(clean: pd.DataFrame) -> pd.DataFrame:
    """依機台彙總（取代手動樞紐分析），欄位與 VBA Summary 分頁相同。"""
    if clean.empty:
        return pd.DataFrame(columns=["EquipmentID", "Readings", "Warnings", "Warning Rate",
                                     "Avg NearestDistance", "Total Cost"])
    g = clean.groupby("EquipmentID", sort=True)
    out = pd.DataFrame({
        "Readings": g.size(),
        "Warnings": g["PredictedStatus"].apply(lambda s: int((s == "Warning").sum())),
        "Avg NearestDistance": g["NearestDistance"].mean(),       # mean 自動略過缺值
        "Total Cost": g["MaintenanceCost"].sum(min_count=0),      # 全缺值時為 0，同 VBA
    })
    out["Warning Rate"] = out["Warnings"] / out["Readings"]
    out = out.reset_index()
    return out[["EquipmentID", "Readings", "Warnings", "Warning Rate",
                "Avg NearestDistance", "Total Cost"]]


# ---------------------------------------------------------------------------
# 對照組：如果手動樞紐漏做清理，會看到什麼
# ---------------------------------------------------------------------------

@dataclass
class NaivePivot:
    """直接拿原始匯出檔做樞紐分析、不 TRIM、不統一大小寫、不去重時的結果。"""

    machine_rows: int          # 樞紐表會出現幾「台」機台
    warning_rows_counted: int  # 只數到字面上是 "Warning" 的列
    status_categories: list[str]
    readings: int              # 未去重的讀數列數


def naive_pivot(folder: Path) -> NaivePivot:
    equips, statuses = [], []
    for path in sorted(folder.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            for i, line in enumerate(fh):
                line = line.rstrip("\r\n")
                if i == 0 or not line.strip():
                    continue
                parts = line.split(DELIM)
                if len(parts) != COL_COUNT:
                    continue
                equips.append(parts[IX_EQUIP])
                statuses.append(parts[IX_STATUS])
    return NaivePivot(
        machine_rows=len(set(equips)),
        warning_rows_counted=sum(1 for s in statuses if s == "Warning"),
        status_categories=sorted(set(statuses)),
        readings=len(statuses),
    )
