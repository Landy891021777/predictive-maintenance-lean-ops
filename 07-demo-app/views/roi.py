"""效益驗證：每一個效益數字怎麼算出來的，假設可以當場調整。

預設值讀自 06-lean-lss/roi-validation.xlsx（單一真相來源），公式與該試算表完全相同，
build/verify_roi.py 驗證可重現校準版（~120 小時／ROI ~200%）與舊版樂觀假設（539 小時／1,248%）。
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from core.cleaning import naive_pivot
from core.data import SAP_LIFECYCLE, load_rpa_runlog, load_validation
from core.roi import compute, error_reduction, load_defaults
from core.ui import ASSUMED, MEASURED, integrity_note, metric_card, page_header

RPA_LABEL = "Power Automate 觸發（1.844 秒）"
KEYS = ["roi_runs", "roi_people", "roi_days", "roi_rate", "roi_dev"]


@st.cache_data
def _defaults():
    return load_defaults()


@st.cache_data
def _naive():
    return naive_pivot(SAP_LIFECYCLE)


def _reset(d) -> None:
    for k, v in zip(KEYS, [d.runs_per_day, d.people, d.workdays, d.hourly_ntd, d.dev_hours]):
        st.session_state[k] = int(v)


# ---------------------------------------------------------------------------
# 第二層：流程自動化 ROI
# ---------------------------------------------------------------------------

def _process_tab() -> None:
    d = _defaults()
    rpa = load_rpa_runlog()
    if KEYS[0] not in st.session_state:
        _reset(d)

    st.markdown(
        "這是本案的**主角**：把每天手動清理彙整報表的工作自動化。"
        "兩個耗時是 🟢 實測值，不可調；其餘使用量與成本是 🟡 假設，拉動滑桿即可看效益怎麼變。"
    )

    left, right = st.columns([2, 3], gap="large")
    with left:
        st.markdown("##### 🟢 實測（固定）")
        st.markdown(f"- 手動清理彙整一次：**{d.manual_s:.0f} 秒**（碼錶實測 15 分鐘）")
        auto_choice = st.radio(
            "自動化單次耗時採用哪一次實測",
            [f"Alt+F8 互動執行（{d.auto_s} 秒，試算表採用）", RPA_LABEL],
            help="兩次都是 VBA 巨集內建 Timer 的真實量測，差異為單次執行的正常波動。",
        )
        auto_s = float(rpa["Elapsed seconds"]) if auto_choice == RPA_LABEL else d.auto_s

        st.markdown("##### 🟡 假設（可調）")
        runs = st.slider("每天執行次數", 1, 10, key=KEYS[0])
        people = st.slider("做同樣作業的人數", 1, 10, key=KEYS[1])
        days = st.slider("年工作天", 200, 260, key=KEYS[2])
        rate = st.slider("人力成本（NT$／小時，全負擔）", 300, 1500, step=50, key=KEYS[3])
        dev = st.slider("一次性導入工時（小時）", 8, 120, key=KEYS[4],
                        help="需求釐清、巨集開發（AI 輔助約 8 小時）、測試、Power Automate 串接、看板、文件與推廣訓練")
        st.button("重設為試算表預設值", on_click=_reset, args=(d,))

    i = d.with_(auto_s=auto_s, runs_per_day=runs, people=people, workdays=days,
                hourly_ntd=rate, dev_hours=dev)
    r = compute(i)

    with right:
        c1, c2 = st.columns(2)
        with c1:
            metric_card("年省工時", f"{r.annual_hours:,.0f} 小時", f"單次省 {r.saved_s:.1f} 秒", ASSUMED)
            metric_card("首年 ROI", f"{r.roi:.0%}", f"首年淨效益 NT${r.net_first_year:,.0f}", ASSUMED)
        with c2:
            metric_card("年省人力成本", f"NT${r.annual_ntd:,.0f}", f"導入成本 NT${r.cost_ntd:,.0f}", ASSUMED)
            metric_card("回本時間", f"{r.payback_days:.0f} 工作天", f"約 {r.payback_days / (days / 12):.1f} 個月", ASSUMED)

        st.markdown("##### 公式（與 roi-validation.xlsx 相同）")
        st.code(
            f"單次省時   = {d.manual_s:.0f} − {auto_s} = {r.saved_s:.1f} 秒\n"
            f"年省工時   = {r.saved_s:.1f} × {runs} 次 × {people} 人 × {days} 天 ÷ 3600 = {r.annual_hours:,.1f} 小時\n"
            f"年省成本   = {r.annual_hours:,.1f} × NT${rate} = NT${r.annual_ntd:,.0f}\n"
            f"導入成本   = {dev} 小時 × NT${rate} = NT${r.cost_ntd:,.0f}\n"
            f"回本工作天 = {r.cost_ntd:,.0f} ÷ ({r.annual_ntd:,.0f} ÷ {days}) = {r.payback_days:.1f}\n"
            f"首年 ROI   = ({r.annual_ntd:,.0f} − {r.cost_ntd:,.0f}) ÷ {r.cost_ntd:,.0f} = {r.roi:.1%}",
            language="text",
        )

        # 敏感度：ROI 對每天執行次數
        sens = pd.DataFrame([{"每天執行次數": n, "首年 ROI": compute(i.with_(runs_per_day=n)).roi * 100}
                             for n in range(1, 11)])
        line = alt.Chart(sens).mark_line(point=True).encode(
            x=alt.X("每天執行次數:Q", scale=alt.Scale(domain=[1, 10])),
            y=alt.Y("首年 ROI:Q", title="首年 ROI（%）"),
            tooltip=["每天執行次數", alt.Tooltip("首年 ROI:Q", format=".0f")],
        )
        here = alt.Chart(pd.DataFrame({"x": [runs], "y": [r.roi * 100]})).mark_point(
            size=220, filled=True, color="#d6453d").encode(x="x:Q", y="y:Q")
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(strokeDash=[4, 4], color="#888").encode(y="y:Q")
        st.altair_chart((line + here + zero).properties(height=220), width="stretch")
        st.caption("ROI 隨使用頻率線性變化；紅點為目前設定，虛線為損益兩平。其他假設固定在左側設定。")

    st.divider()
    st.markdown("##### 為什麼預設是「1 人 × 每天 2 次」")
    old = compute(d.with_(people=3, runs_per_day=3))
    cur = compute(d)
    st.dataframe(pd.DataFrame([
        {"版本": "早期草稿（已棄用）", "假設": "3 人 × 每天 3 次", "年省工時": f"{old.annual_hours:,.0f}",
         "首年 ROI": f"{old.roi:.0%}", "回本": f"{old.payback_days:.0f} 工作天"},
        {"版本": "校準版（試算表預設）", "假設": f"{d.people:.0f} 人 × 每天 {d.runs_per_day:.0f} 次",
         "年省工時": f"{cur.annual_hours:,.0f}", "首年 ROI": f"{cur.roi:.0%}",
         "回本": f"{cur.payback_days:.0f} 工作天"},
    ]), hide_index=True, width="stretch")
    st.caption(
        "早期版本假設 3 人各跑 3 次，ROI 衝到 1,248%；精實改善案給出這種數字反而不可信，因此下修為保守的使用量。"
        "唯一的實測值是單次省時，年省工時、ROI、回本天數都建立在使用量假設上。"
    )



# ---------------------------------------------------------------------------
# 第一層：設備健康 84% / 36%
# ---------------------------------------------------------------------------

def _health_tab() -> None:
    v = load_validation()
    hh, pred_h, true_h = int(v.cm[0, 0]), int(v.cm[:, 0].sum()), int(v.cm[0].sum())
    p_exact, r_exact = hh / pred_h, hh / true_h

    st.markdown(
        "這是本案的**技術亮點**，屬於 🟡 **情境推估**：公開資料集沒有真實維修成本，"
        "所以不能說「省了多少錢」，只能用 value-driver 公式推估**錯誤比例降了幾成**。"
    )

    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        st.markdown("##### 公開基準（可調）")
        base_p = st.slider("基準 Precision(Healthy)", 0.50, 0.95, 0.75, 0.01, format="%.2f")
        base_r = st.slider("基準 Recall(Healthy)", 0.50, 0.95, 0.70, 0.01, format="%.2f")
        st.caption(
            "預設 75% / 70% 依據原始 Kaggle notebook（wassimderbel/nasa-predictive-maintenance-rul）"
            "的分類段落；該段各模型的 macro precision 約 0.66–0.72、recall 約 0.65–0.71。"
        )
        st.markdown("##### 本專案 VAE（🟢 實測）")
        rounded = st.radio("使用哪一組數值", ["取整：96% / 81%（履歷採用）",
                                          f"未取整：{p_exact:.2%} / {r_exact:.2%}"])
        use_round = rounded.startswith("取整")
        vae_p, vae_r = (0.96, 0.81) if use_round else (p_exact, r_exact)
        st.caption(f"Precision(Healthy) = {hh}/{pred_h}，Recall(Healthy) = {hh}/{true_h}（由混淆矩陣計算）")

    cost = error_reduction(base_p, vae_p)
    down = error_reduction(base_r, vae_r)

    with c2:
        m1, m2 = st.columns(2)
        with m1:
            metric_card("維護成本降低", f"{cost:.1%}", "漏判造成的非計畫維修", ASSUMED)
        with m2:
            metric_card("停機時間降低", f"{down:.1%}", "不必要的拉機檢查", ASSUMED)
        st.markdown("##### 推導")
        st.code(
            f"漏判比例 = 1 − Precision(Healthy)   判為健康、其實在衰退 → 非計畫故障的維護成本\n"
            f"  基準 {1 - base_p:.1%} → 本模型 {1 - vae_p:.1%}\n"
            f"  降幅 = ({1 - base_p:.4f} − {1 - vae_p:.4f}) ÷ {1 - base_p:.4f} = {cost:.1%}\n\n"
            f"過度維修 = 1 − Recall(Healthy)      其實健康、卻被叫去檢修 → 不必要的停機\n"
            f"  基準 {1 - base_r:.1%} → 本模型 {1 - vae_r:.1%}\n"
            f"  降幅 = ({1 - base_r:.4f} − {1 - vae_r:.4f}) ÷ {1 - base_r:.4f} = {down:.1%}",
            language="text",
        )
        if use_round and abs(base_p - 0.75) < 1e-9 and abs(base_r - 0.70) < 1e-9:
            st.caption("履歷中的 84% 即此處的 84.0%；36% 為 36.7% 捨去小數。未取整計算則約為 85.7% 與 35.3%。")

    st.markdown("##### 限制與但書")
    st.markdown(
        """
- **情境推估，不是實測**：公開資料集沒有真實維修成本，這裡只推估錯誤比例的降幅
- **評估方式不同**：公開基準是 3 分類（RUL ≤68 / 69–137 / >137）、在 7,221 筆上評估；
  本專案是 2 分類、在 100 台引擎的最後一個 cycle 上評估
- **二分類是刻意的設計取捨**：現場需要的是「要不要處理」的決策，而非精確的剩餘壽命數字
- **對基準很敏感**：可以拉動左側滑桿看降幅怎麼變 —— 這正是它只能當情境推估的原因
        """
    )

    grid = pd.DataFrame([{
        "基準 Precision": f"{bp:.0%}",
        **{f"本模型 {vp:.0%}": f"{error_reduction(bp, vp):.0%}" for vp in (0.90, 0.93, 0.96)},
    } for bp in (0.70, 0.75, 0.80, 0.85)])
    st.markdown("##### 敏感度：維護成本降幅對基準的依賴")
    st.dataframe(grid, hide_index=True, width="stretch")
    st.caption("基準越好，同樣的模型表現能換到的降幅越小；基準若達 85%，96% 的模型只剩約 73% 的降幅。")


# ---------------------------------------------------------------------------
# 品質效益
# ---------------------------------------------------------------------------

def _quality_tab() -> None:
    rpa = load_rpa_runlog()
    n = _naive()
    st.markdown(
        "時間不是自動化唯一的效益。手動流程最危險的是**出錯時 Excel 不會報錯** —— 這一項是 🟢 實測，"
        "直接由原始匯出檔計算，不需要任何假設。"
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("狀態大小寫修正", f"{int(rpa['Status case normalized']):,} 筆",
                    "Warning / warning / WARNING 混用", MEASURED)
    with c2:
        metric_card("去除重複列", f"{int(rpa['Duplicate rows removed']):,} 筆", "以日期｜機台｜Cycle｜時戳｜工單去重", MEASURED)
    with c3:
        metric_card("漏做清理時的機台數", f"{n.machine_rows} 台", "實際 100 台", MEASURED)
    with c4:
        metric_card("漏做清理時的 Warning", f"{n.warning_rows_counted:,} 筆",
                    f"實際 {int(rpa['Total WARNING readings']):,} 筆", MEASURED)
    integrity_note("完整展示見「自動化」頁：可以按鈕實際執行清理，並與 Power Automate 的實際產出逐項對照。")


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def render() -> None:
    page_header(
        "效益驗證",
        "每一個效益數字怎麼算出來的：流程自動化的 ROI、消除的靜默錯誤、以及設備健康的 84% / 36%。"
        "公式全部攤開，假設可以當場調整。",
        "reduced maintenance costs by 84% and equipment downtime by 36%",
    )
    t1, t2, t3 = st.tabs(["流程自動化 ROI（主角）", "品質效益", "設備健康 84% / 36%（情境推估）"])
    with t1:
        _process_tab()
    with t2:
        _quality_tab()
    with t3:
        _health_tab()
    integrity_note(
        "兩層效益分列、不混算：流程自動化的耗時與錯誤筆數為實測；ROI 與設備健康效益建立在假設或公開基準上。"
        "預設值讀自 06-lean-lss/roi-validation.xlsx。"
    )
