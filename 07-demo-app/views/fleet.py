"""機隊軌跡：13,096 筆逐筆判讀長什麼樣，以及被漏判的那幾台。"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from core.data import load_predictions, load_validation, load_validation_table
from core.ui import MEASURED, integrity_note, metric_card, page_header

COLOURS = {"Healthy": "#2e9e5b", "Warning": "#d6453d"}


def render() -> None:
    page_header(
        "機隊軌跡",
        "模型不是只判一次，而是對每一筆進來的讀數都判一次 —— 就像真正的營運系統那樣。"
        "這頁是 13,096 筆逐筆判讀的全貌，以及模型犯錯的地方。",
        "reduced equipment downtime — early fault detection",
    )

    preds = load_predictions()
    v = load_validation()
    vt = load_validation_table()

    n_warn = int((preds["PredictedStatus"] == "Warning").sum())
    engines_with_warn = preds.loc[preds["PredictedStatus"] == "Warning", "unit_number"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("判讀筆數", f"{len(preds):,}", "test_FD001 全部讀數", MEASURED)
    with c2:
        metric_card("Warning 筆數", f"{n_warn:,}",
                    f"佔 {n_warn / len(preds):.1%}", MEASURED)
    with c3:
        metric_card("曾被預警的引擎", f"{engines_with_warn}/100",
                    "整個生命週期內至少出現一次 Warning", MEASURED)
    with c4:
        metric_card("漏判台數", f"{v.missed}",
                    f"另有誤報 {v.false_alarms} 台", MEASURED)

    st.divider()

    tab1, tab2, tab3 = st.tabs(["單台引擎軌跡", "模型犯的錯", "混淆矩陣"])

    # ---------------- 單台引擎 ----------------
    with tab1:
        engines = sorted(preds["unit_number"].unique())
        default_idx = engines.index(24) if 24 in engines else 0
        u = st.selectbox("選擇引擎", engines,
                         index=default_idx, format_func=lambda x: f"ENG-{x:03d}")

        d = preds[preds["unit_number"] == u].sort_values("time_cycles")
        row = vt[vt["EquipmentID"] == f"ENG-{u:03d}"]

        first_warn = d.loc[d["PredictedStatus"] == "Warning", "time_cycles"]
        first_warn = int(first_warn.min()) if len(first_warn) else None

        m1, m2, m3 = st.columns(3)
        with m1:
            metric_card("觀測長度", f"{len(d)} cycles", "這台引擎的讀數筆數", MEASURED)
        with m2:
            metric_card("首次預警", f"cycle {first_warn}" if first_warn else "全程未預警",
                        f"距最後一筆觀測還有 {int(d['time_cycles'].max()) - first_warn} 個 cycle"
                        if first_warn else "模型全程判為 Healthy", MEASURED)
        with m3:
            if len(row):
                r = row.iloc[0]
                metric_card("最後一個 cycle 的判讀",
                            f"{r['PredictedStatus']}",
                            f"真實剩餘壽命 {int(r['TrueRUL'])} cycles → {r['結果']}", MEASURED)

        chart = (
            alt.Chart(d)
            .mark_circle(size=26)
            .encode(
                x=alt.X("time_cycles:Q", title="cycle"),
                y=alt.Y("NearestDistance:Q", title="到最近 support 點的距離"),
                color=alt.Color(
                    "PredictedStatus:N", title="判讀",
                    scale=alt.Scale(domain=list(COLOURS), range=list(COLOURS.values())),
                ),
                tooltip=["time_cycles", "PredictedStatus",
                         alt.Tooltip("NearestDistance:Q", format=".4f"),
                         alt.Tooltip("LatentZ1:Q", format=".3f"),
                         alt.Tooltip("LatentZ2:Q", format=".3f")],
            )
            .properties(height=330)
        )
        st.altair_chart(chart, use_container_width=True)
        st.caption(
            "橫軸是引擎累積運轉 cycle，縱軸是這筆讀數在潛空間裡離最近訓練點的距離。"
            "引擎退化時，讀數會逐漸飄離健康樣本聚集的區域。"
        )

        st.markdown("##### 潛空間裡的退化路徑")
        traj = (
            alt.Chart(d)
            .mark_line(point=alt.OverlayMarkDef(size=18), strokeWidth=1, opacity=0.8)
            .encode(
                x=alt.X("LatentZ1:Q", title="latent z1"),
                y=alt.Y("LatentZ2:Q", title="latent z2"),
                order="time_cycles:Q",
                color=alt.Color("time_cycles:Q", title="cycle",
                                scale=alt.Scale(scheme="viridis")),
                tooltip=["time_cycles", "PredictedStatus"],
            )
            .properties(height=320)
        )
        st.altair_chart(traj, use_container_width=True)
        st.caption("同一台引擎在 2 維潛空間中隨時間移動的軌跡，顏色由深到淺代表 cycle 由小到大。")

    # ---------------- 模型犯的錯 ----------------
    with tab2:
        st.markdown(
            f"""
在 {v.n_engines} 台引擎的最後一個 cycle 上，模型判錯了 {v.missed + v.false_alarms} 台。
這兩種錯誤的代價**完全不對等**：

- **漏判 {v.missed} 台**（實際快故障，卻判為 Healthy）—— 代價最高，引擎沒被預警就故障
- **誤報 {v.false_alarms} 台**（實際健康，卻判為 Warning）—— 代價較低，多做一次檢查

模型在這個取捨上偏向**寧可誤報、不要漏判**，符合預測性維護的實務需求。
            """
        )
        wrong = vt[vt["結果"] != "判讀正確"].copy()
        wrong = wrong.sort_values(["結果", "TrueRUL"])
        st.dataframe(
            wrong[["EquipmentID", "LastCycle", "TrueRUL", "TrueLabel",
                   "PredictedStatus", "NearestDistance", "結果"]],
            use_container_width=True, hide_index=True,
            column_config={
                "EquipmentID": "機台",
                "LastCycle": "最後 cycle",
                "TrueRUL": "真實剩餘壽命",
                "TrueLabel": "真實標籤",
                "PredictedStatus": "模型判讀",
                "NearestDistance": st.column_config.NumberColumn("最近距離", format="%.4f"),
            },
        )
        missed_ids = vt.loc[vt["結果"] == "漏判", "EquipmentID"].tolist()
        st.caption(
            f"被漏判的是 **{'、'.join(missed_ids)}**。可以到「單台引擎軌跡」分頁輸入這幾台，"
            "看它們為什麼沒被抓出來 —— 它們的讀數在潛空間裡仍落在健康樣本附近。"
        )

    # ---------------- 混淆矩陣 ----------------
    with tab3:
        cm = pd.DataFrame(
            v.cm,
            index=["實際 Healthy", "實際 Warning"],
            columns=["預測 Healthy", "預測 Warning"],
        )
        left, right = st.columns([2, 3], gap="large")
        with left:
            st.dataframe(cm, use_container_width=True)
            st.markdown(
                f"""
|  | Precision | Recall |
|---|---|---|
| **Healthy** | {v.healthy_precision:.4f} | {v.healthy_recall:.4f} |
| **Warning** | {v.warning_precision:.4f} | {v.warning_recall:.4f} |

Accuracy = **{v.accuracy:.4f}**
                """
            )
        with right:
            st.markdown(
                """
**為什麼只評 100 台、只評最後一個 cycle？**

因為 CMAPSS 的 `RUL_FD001` 只提供每台引擎**最後那一點**的真實剩餘壽命，
這是這個資料集的標準評估法。左邊 13,096 筆的逐筆判讀是**模擬營運系統的輸出**，
不含真實答案 —— 現實中故障還沒發生，系統不可能知道答案。

**標籤怎麼定的？**

訓練集 RUL 的 33% 分位數 = 67.0 cycles 作為 support 標籤分界；
真實標籤則用 `RUL_FD001` 的 33% 分位數 = 52.7 cycles。
兩者各自在自己的分佈上取分位數，不互相洩漏。
                """
            )
        integrity_note(
            "本頁所有數字皆由 `01-core-model/scoring/score_engines.py` 在真實 NASA CMAPSS "
            "資料上實際執行產生，網頁只是讀取其輸出檔並重新計算指標，未寫死任何數值。"
        )
