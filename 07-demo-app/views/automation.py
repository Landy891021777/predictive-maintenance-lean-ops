"""自動化：髒的匯出檔 → 一鍵清理彙總 → 報表，並陳 Power Automate 實際執行的證據。

雲端沒有 Windows / Excel，無法執行 VBA 與 Power Automate Desktop。
本頁的「執行」按鈕跑的是 core/cleaning.py —— 同一套規則的 Python 重現，
已由 build/verify_cleaning.py 對照 Power Automate 實際產出的報表逐項驗證一致。
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core.cleaning import (
    COL_COUNT, DELIM, IX_COST, IX_DATE, IX_DIST, IX_EQUIP, IX_STATUS,
    naive_pivot, normalize_date, run_pipeline,
)
from core.data import (
    PAD_SCREENSHOT, SAP_LIFECYCLE,
    load_raw_export_lines, load_rpa_runlog,
)
from core.ui import MEASURED, integrity_note, metric_card, page_header

RESULT_KEY = "automation_result"

MANUAL_SECONDS = 900        # 🟢 碼錶實測：手動清理彙整一次 15 分鐘
VBA_INTERACTIVE = 1.6       # 🟢 Alt+F8 互動執行，記錄於 02-automation-vba/README.md（commit 50d3247）


# ---------------------------------------------------------------------------
# 原始檔樣本：挑出每一種髒資料的第一個實例
# ---------------------------------------------------------------------------

def _visible(s: str) -> str:
    """把前後空白顯示出來，否則表格裡看不到問題在哪。"""
    return s.replace(" ", "␣")


def _dirty_samples(lines: list[str]) -> pd.DataFrame:
    wanted = {
        "機台代號前後有空白": lambda p: p[IX_EQUIP] != p[IX_EQUIP].strip(),
        "機台代號小寫": lambda p: p[IX_EQUIP].strip() != p[IX_EQUIP].strip().upper(),
        "狀態全小寫": lambda p: p[IX_STATUS].strip() in ("warning", "healthy"),
        "狀態全大寫": lambda p: p[IX_STATUS].strip() in ("WARNING", "HEALTHY"),
        "日期格式 yyyy/mm/dd": lambda p: "/" in p[IX_DATE],
        "日期格式 dd-Mon-yyyy": lambda p: "-" in p[IX_DATE] and len(p[IX_DATE].split("-")[0]) != 4,
        "成本含千分位逗號": lambda p: "," in p[IX_COST],
        "成本缺值": lambda p: not p[IX_COST].strip(),
        "距離缺值": lambda p: not p[IX_DIST].strip(),
    }
    found: dict[str, tuple[int, list[str]]] = {}
    seen_keys: dict[str, int] = {}
    dup: tuple[int, int] | None = None

    for n, line in enumerate(lines[1:], start=2):
        p = line.split(DELIM)
        if len(p) != COL_COUNT:
            continue
        for label, test in wanted.items():
            if label not in found and test(p):
                found[label] = (n, p)
        d = normalize_date(p[IX_DATE])
        if d and dup is None:
            key = "|".join([d.isoformat(), p[IX_EQUIP].strip().upper(),
                            p[2].strip(), p[3].strip(), p[20].strip()])
            if key in seen_keys:
                dup = (seen_keys[key], n)
            else:
                seen_keys[key] = n
        if len(found) == len(wanted) and dup:
            break

    # 每一列只出現一次，並列出它命中的「所有」問題（一列常同時有好幾種髒資料）
    selected = {n for n, _ in found.values()}
    extra: dict[int, str] = {}
    if dup:
        selected |= set(dup)
        extra[dup[0]] = "重複列（第一筆，保留）"
        extra[dup[1]] = f"重複列（與第 {dup[0]} 行相同，移除）"

    out = []
    for n in sorted(selected):
        p = lines[n - 1].split(DELIM)
        labels = [label for label, test in wanted.items() if test(p)]
        if n in extra:
            labels.append(extra[n])
        out.append({
            "原始行號": n,
            "ExportDate": p[IX_DATE],
            "EquipmentID": _visible(p[IX_EQUIP]),
            "PredictedStatus": p[IX_STATUS],
            "NearestDistance": p[IX_DIST] or "（空）",
            "MaintenanceCost": p[IX_COST] or "（空）",
            "問題": "、".join(labels),
        })
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# 報表輸出
# ---------------------------------------------------------------------------

def _excel_report(result) -> bytes:
    """產生與 VBA Summary 分頁同結構的每日報表。"""
    log = result.log
    runlog = pd.DataFrame([
        ("Files read", log.files_read),
        ("Raw rows read", log.rows_read),
        ("Duplicate rows removed", log.duplicates_removed),
        ("Clean rows", log.clean_rows),
        ("Status case normalized", log.status_normalized),
        ("Total WARNING readings", log.total_warnings),
        ("Missing NearestDistance", log.missing_distance),
        ("Missing MaintenanceCost", log.missing_cost),
        ("Elapsed seconds (Python, web)", round(log.elapsed_seconds, 3)),
    ], columns=["Item", "Value"])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        runlog.to_excel(xw, sheet_name="Summary", index=False, startrow=0)
        result.summary.to_excel(xw, sheet_name="Summary", index=False, startrow=len(runlog) + 3)
        ws = xw.sheets["Summary"]
        ws.cell(row=len(runlog) + 3, column=1, value="Per-equipment summary")
        ws.column_dimensions["A"].width = 30
        for col in "BCDEF":
            ws.column_dimensions[col].width = 18
    return buf.getvalue()


@st.cache_data
def _naive():
    return naive_pivot(SAP_LIFECYCLE)


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def render() -> None:
    page_header(
        "自動化",
        "工程師每天要做的事：下載 SAP-style 匯出檔、在 Excel 裡清理髒資料、做樞紐分析彙總、寄報表。"
        "這一頁把那整段流程變成一個按鈕，並讓你看到手動做時會悄悄出錯的地方。",
        "Automated reporting via RPA/Power Automate",
    )

    rpa = load_rpa_runlog()
    rpa_seconds = float(rpa["Elapsed seconds"])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("手動清理彙整一次", "15 分鐘", "碼錶實測，13,750 列", MEASURED)
    with c2:
        metric_card("VBA 巨集一次", f"{VBA_INTERACTIVE} 秒",
                    f"RPA 無人值守執行實測 {rpa_seconds:.3f} 秒", MEASURED)
    with c3:
        metric_card("提速倍數", "約 500×",
                    f"兩次實測：互動 {MANUAL_SECONDS / VBA_INTERACTIVE:.0f}×／"
                    f"RPA {MANUAL_SECONDS / rpa_seconds:.0f}×", MEASURED)
    with c4:
        metric_card("消除的靜默錯誤", f"{rpa['Status case normalized']:,} 筆",
                    f"另去除重複列 {rpa['Duplicate rows removed']} 筆", MEASURED)

    st.divider()

    # ---------------- ① 原始匯出檔 ----------------
    st.subheader("① 每天進來的原始匯出檔")
    fname, lines = load_raw_export_lines()
    st.markdown(
        f"以下是 `{fname}` 裡挑出的原始列，**每一種髒資料各取第一個實例**。"
        "機台代號的空白以 `␣` 顯示 —— 在 Excel 裡它們是隱形的。"
    )
    st.dataframe(_dirty_samples(lines), width="stretch", hide_index=True)
    integrity_note(
        "感測值、機台編號、模型判讀（PredictedStatus）為真實計算結果；"
        "匯出日期、工單號、維護成本與上述髒資料為模擬。本案**未串接真實 SAP 系統**，"
        "此檔格式仿照 SAP 匯出（分號分隔，避免千分位逗號破壞欄位）。"
    )

    st.divider()

    # ---------------- ② 一鍵清理 ----------------
    st.subheader("② 按一下，跑一次自動清理")
    st.markdown(
        "讀取 3 個匯出檔 → 統一日期格式 → 機台代號去空白並轉大寫 → 統一狀態大小寫 → "
        "去千分位 → 以「日期｜機台｜Cycle｜時戳｜工單」去重 → 依機台彙總。"
    )

    if st.button("▶ 執行自動清理", type="primary"):
        with st.spinner("清理中…"):
            result = run_pipeline(SAP_LIFECYCLE)
            st.session_state[RESULT_KEY] = (result, _excel_report(result))

    if RESULT_KEY in st.session_state:
        result, xlsx = st.session_state[RESULT_KEY]
        log = result.log

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("原始列", f"{log.rows_read:,}")
        m2.metric("去除重複", f"{log.duplicates_removed:,}")
        m3.metric("乾淨列", f"{log.clean_rows:,}")
        m4.metric("Warning 總數", f"{log.total_warnings:,}")
        st.caption(
            f"本次在網頁伺服器上以 Python 執行耗時 **{log.elapsed_seconds:.2f} 秒**。"
            "這個數字**不用於效益計算** —— 執行環境不同；ROI 用的是 VBA 在本機 Excel 的實測值。"
        )

        st.markdown("##### 與 Power Automate 實際跑出的報表對照")
        compare = pd.DataFrame([
            ("讀取檔案數", log.files_read, rpa["Files read"]),
            ("原始列", log.rows_read, rpa["Raw rows read"]),
            ("去除重複列", log.duplicates_removed, rpa["Duplicate rows removed"]),
            ("乾淨列", log.clean_rows, rpa["Clean rows"]),
            ("狀態大小寫修正", log.status_normalized, rpa["Status case normalized"]),
            ("Warning 總數", log.total_warnings, rpa["Total WARNING readings"]),
            ("缺 NearestDistance", log.missing_distance, rpa["Missing NearestDistance"]),
            ("缺 MaintenanceCost", log.missing_cost, rpa["Missing MaintenanceCost"]),
        ], columns=["項目", "網頁上的 Python 重現", "本機 VBA（經 RPA 觸發）"])
        compare["一致"] = (compare.iloc[:, 1] == compare.iloc[:, 2]).map({True: "✓", False: "✗"})
        st.dataframe(compare, width="stretch", hide_index=True)
        st.caption(
            "右欄讀自 `03-rpa-power-automate/outbox/DailyHealthReport_20260711.xlsm` 的 Summary 分頁，"
            "那是 Power Automate Desktop 在本機觸發 Excel 執行巨集後實際產出的報表。"
        )

        t1, t2, t3 = st.tabs(["機台彙總", "清理後資料", "下載報表"])
        with t1:
            shown = result.summary.assign(**{"Warning Rate": result.summary["Warning Rate"] * 100})
            st.dataframe(
                shown, width="stretch", hide_index=True,
                column_config={
                    "Warning Rate": st.column_config.ProgressColumn(
                        "Warning Rate", format="%.1f%%", min_value=0, max_value=100),
                    "Avg NearestDistance": st.column_config.NumberColumn(format="%.6f"),
                    "Total Cost": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        with t2:
            st.caption(f"共 {len(result.clean):,} 列，以下顯示前 300 列。")
            st.dataframe(result.clean.head(300), width="stretch", hide_index=True)
        with t3:
            d1, d2 = st.columns(2)
            d1.download_button(
                "下載每日報表（Excel）", xlsx,
                file_name="DailyHealthReport_web.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
            d2.download_button(
                "下載清理後資料（CSV）",
                result.clean.to_csv(index=False).encode("utf-8-sig"),
                file_name="CleanData.csv", mime="text/csv", width="stretch",
            )
    else:
        st.info("按下上方按鈕，實際執行一次清理。")

    st.divider()

    # ---------------- ③ 手動漏一步會怎樣 ----------------
    st.subheader("③ 如果手動做，漏了一步")
    n = _naive()
    clean_warnings = int(rpa["Total WARNING readings"])
    st.markdown(
        "手動流程最危險的不是慢，而是**出錯時 Excel 不會報錯**。"
        "如果直接拿原始檔做樞紐分析、忘了 `TRIM` 和統一大小寫，報表看起來完成了，數字卻是錯的："
    )
    x1, x2, x3 = st.columns(3)
    with x1:
        metric_card("樞紐表上的機台數", f"{n.machine_rows} 台",
                    "實際只有 100 台 —— 同一台被拆成好幾列", MEASURED)
    with x2:
        metric_card("樞紐表數到的 Warning", f"{n.warning_rows_counted:,} 筆",
                    f"清理後實際 {clean_warnings:,} 筆", MEASURED)
    with x3:
        metric_card("狀態欄出現幾種寫法", f"{len(n.status_categories)} 種",
                    "、".join(n.status_categories), MEASURED)
    st.markdown(
        "這不是假設情境：建立手動基線時真的發生過 —— `Ctrl+H` 的空白取代沒生效，"
        "樞紐分析把 `␣␣ENG-001␣` 和 `ENG-001` 當成兩台機台，**而 Excel 沒有跳出任何錯誤訊息**。"
        "漏算一筆 Warning，代價可能是一台引擎的非計畫停機。"
    )
    integrity_note(
        "以上三個數字由網頁直接對原始匯出檔計算（不清理、不去重），非估計值。"
        "Warning 數在未去重的情況下仍然少算，是因為大小寫不一致的影響大於重複列的灌水。"
    )

    st.divider()

    # ---------------- ④ Power Automate ----------------
    st.subheader("④ 在本機真的跑過的 Power Automate 流程")
    left, right = st.columns([3, 2], gap="large")
    with left:
        if PAD_SCREENSHOT.exists():
            st.image(str(PAD_SCREENSHOT),
                     caption="Power Automate Desktop 流程 DailyHealthReport（畫面為第 3–8 步）",
                     width="stretch")
    with right:
        st.markdown(
            """
**實際採用的流程（as-built）**

1. 開啟 Excel，執行無對話框的巨集 `CleanAndSummarizeSilent`
2. 儲存並關閉 Excel
3. 取得當日日期，轉成 `yyyyMMdd`
4. 複製報表到 `outbox\\`
5. 重新命名為 `DailyHealthReport_yyyyMMdd.xlsm`
6. 桌面通知「報表已產生於 outbox」

**一個真實的工程細節**：RPA 遇到彈窗會卡住等人點。
所以巨集另外提供了**不跳任何對話框**的進入點 `CleanAndSummarizeSilent`，
才能從「人工按的巨集」升級成「無人值守的流程」。
            """
        )
    integrity_note(
        "雲端環境沒有 Windows 與 Excel，**無法執行 Power Automate Desktop 或 VBA**，"
        "因此本頁的按鈕跑的是同一套清理規則的 Python 重現，並已與上方 RPA 實際產出逐項比對一致。"
        "「從 SAP 下載」在本機流程中以複製檔案模擬；分發採存檔加桌面通知，未串接 Email。"
    )

    with st.expander("耗時數字的出處"):
        st.markdown(
            f"""
| 情境 | 耗時 | 出處 | 用途 |
|---|---|---|---|
| 手動清理彙整 | 900 秒 | 碼錶實測 🟢 | ROI 基線 |
| VBA 互動執行（Alt+F8） | {VBA_INTERACTIVE} 秒 | 巨集內建 `Timer`，記錄於 `02-automation-vba/README.md` 🟢 | ROI 計算 |
| VBA 經 Power Automate 觸發 | {rpa_seconds:.3f} 秒 | RPA 產出報表 `Summary!B9` 🟢 | 佐證 |
| Python 重現（本網頁） | 每次不同 | 網頁伺服器即時量測 | 僅供參考，不計入效益 |

兩次 VBA 執行的差異來自單次執行的正常波動。以互動執行計提速約 **{MANUAL_SECONDS / VBA_INTERACTIVE:.0f}×**，
以 RPA 那次計約 **{MANUAL_SECONDS / rpa_seconds:.0f}×**，量級一致。

> 效益不應用「資料量 × 倍數」推算。Excel 的取代、移除重複、樞紐分析都是整欄批次操作，
> 人工點擊次數不隨列數成長。真正的效益是**品質**（不再靜默少算）與**可規模化**。
            """
        )
