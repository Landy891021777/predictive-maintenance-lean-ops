"""
驗證：core/cleaning.py 的 Python 重現，必須與 VBA 巨集的實際產出逐項一致。

對照組是 Power Automate Desktop 實際跑出來的報表：
    03-rpa-power-automate/outbox/DailyHealthReport_20260711.xlsm
其中 Summary 分頁由 CleanAndSummarizeSilent 在本機 Excel 中產生。

檢查項目：
  [A] run log 的 8 個計數（檔案數、原始列、去重、乾淨列、大小寫修正、
      Warning 總數、缺距離、缺成本）
  [B] 100 台機台的彙總表：讀數、警告數完全相同；
      警告率、平均距離、成本合計誤差 < 1e-6（浮點累加順序差異）

執行：py -3 07-demo-app/build/verify_cleaning.py
相依：openpyxl（讀 .xlsm）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

APP = Path(__file__).resolve().parent.parent
REPO = APP.parent
sys.path.insert(0, str(APP))
from core.cleaning import naive_pivot, run_pipeline  # noqa: E402

LIFECYCLE = REPO / "02-automation-vba" / "sample-data" / "lifecycle"
RPA_REPORT = REPO / "03-rpa-power-automate" / "outbox" / "DailyHealthReport_20260711.xlsm"


def read_rpa_report() -> tuple[dict, pd.DataFrame]:
    wb = openpyxl.load_workbook(RPA_REPORT, read_only=True, data_only=True)
    rows = list(wb["Summary"].iter_rows(values_only=True))
    log = {r[0]: r[1] for r in rows[1:10] if r[0]}
    header_idx = next(i for i, r in enumerate(rows) if r[0] == "EquipmentID")
    body = [r[:6] for r in rows[header_idx + 1:] if r[0]]
    summary = pd.DataFrame(body, columns=list(rows[header_idx][:6]))
    return log, summary


def main() -> int:
    result = run_pipeline(LIFECYCLE)
    log = result.log
    rpa_log, rpa_summary = read_rpa_report()

    # ---------- [A] run log ----------
    pairs = [
        ("Files read", log.files_read),
        ("Raw rows read", log.rows_read),
        ("Duplicate rows removed", log.duplicates_removed),
        ("Clean rows", log.clean_rows),
        ("Status case normalized", log.status_normalized),
        ("Total WARNING readings", log.total_warnings),
        ("Missing NearestDistance", log.missing_distance),
        ("Missing MaintenanceCost", log.missing_cost),
    ]
    print("[A] run log                     Python   RPA 實際產出")
    ok_a = True
    for name, mine in pairs:
        theirs = rpa_log.get(name)
        same = mine == theirs
        ok_a &= same
        print(f"    {name:26s} {mine:8,}   {theirs:>8,}  {'✓' if same else '✗'}")
    print(f"    （Python 版另外揭露：欄位數不符丟棄 {log.dropped_bad_columns}、"
          f"日期無法解析丟棄 {log.dropped_bad_date}）")
    print(f"    RPA 那次的 VBA 實測耗時：{rpa_log.get('Elapsed seconds')} 秒")
    print(f"    本次 Python 重現耗時：  {log.elapsed_seconds:.3f} 秒")

    # ---------- [B] 每台機台彙總 ----------
    mine = result.summary.set_index("EquipmentID")
    theirs = rpa_summary.set_index("EquipmentID")
    ok_b = list(mine.index) == list(theirs.index)
    print(f"\n[B] 機台彙總：Python {len(mine)} 台 / RPA {len(theirs)} 台，"
          f"機台清單{'一致' if ok_b else '不一致'}")

    if ok_b:
        for col in ["Readings", "Warnings"]:
            diff = int((mine[col].astype(int) != theirs[col].astype(int)).sum())
            ok_b &= diff == 0
            print(f"    {col:22s} 不一致 {diff} 台")
        for col in ["Warning Rate", "Avg NearestDistance", "Total Cost"]:
            a = mine[col].astype(float).to_numpy()
            b = pd.to_numeric(theirs[col], errors="coerce").astype(float).to_numpy()
            d = float(np.nanmax(np.abs(a - b)))
            ok_b &= d < 1e-6
            print(f"    {col:22s} 最大誤差 {d:.2e}")

    # ---------- 對照：手動樞紐漏做清理 ----------
    n = naive_pivot(LIFECYCLE)
    print(f"\n[參考] 若直接對原始檔做樞紐（不 TRIM / 不統一大小寫 / 不去重）：")
    print(f"    機台列數 {n.machine_rows}（實際 100 台）")
    print(f"    狀態分類 {n.status_categories}")
    print(f"    Warning 只數到 {n.warning_rows_counted:,} 筆（清理後 {log.total_warnings:,} 筆）")
    print(f"    讀數 {n.readings:,} 列（去重後 {log.clean_rows:,} 列）")

    ok = ok_a and ok_b
    print("\n" + ("✅ Python 重現與 Power Automate 實際產出完全一致"
                  if ok else "❌ 與 RPA 實際產出不一致，不可上線"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
