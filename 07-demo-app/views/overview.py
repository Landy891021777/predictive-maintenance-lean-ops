"""總覽：一頁講完這個專案在解決什麼，以及每個數字是實測還是假設。"""

from __future__ import annotations

import streamlit as st

from core.data import load_predictions, load_validation
from core.ui import ASSUMED, MEASURED, integrity_note, metric_card, page_header

GITHUB = "https://github.com/Landy891021777/predictive-maintenance-lean-ops"


def render() -> None:
    page_header(
        "預測維護 → 精實營運自動化",
        "以 NASA CMAPSS 航太引擎感測資料的 VAE 異常偵測模型為核心，"
        "延伸成一套 DMAIC 精實改善案：模型負責判讀設備健康，自動化流程負責把判讀結果"
        "變成每天真的有人在看的報表。這個網站讓你自己動手驗證其中每一個數字。",
    )

    v = load_validation()
    preds = load_predictions()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("模型準確率", f"{v.accuracy:.1%}",
                    f"{v.n_engines} 台引擎，最後一個 cycle", MEASURED)
    with c2:
        metric_card("快故障召回率", f"{v.warning_recall:.1%}",
                    f"{v.cm[1,1]}/{v.cm[1].sum()} 台抓到，漏判 {v.missed} 台", MEASURED)
    with c3:
        metric_card("資料處理提速", "約 500×",
                    "原始 13,750 列：手動 15 分 → 自動約 1.6–1.8 秒", MEASURED)
    with c4:
        metric_card("首年 ROI", "約 200%",
                    "年省約 120 小時；假設可在「效益驗證」頁調整", ASSUMED)

    st.divider()

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("這個專案在解決什麼")
        st.markdown(
            """
製造與半導體現場常見**兩層浪費**，這個專案兩層都處理，但主從分明：

| 層 | 浪費 | 解法 | 在本案的角色 |
|---|---|---|---|
| **第二層｜流程浪費** | 工程師每天手動下載匯出檔、Excel 彙整、人工判讀、手動寄報表 | VBA + Power Automate (RPA) + Power BI | **主角**，效益可實測 |
| **第一層｜實體浪費** | 設備非計畫停機、過度保養 | VAE 異常偵測模型自動判讀健康狀態 | **技術亮點**，效益為情境假設 |

主從關係：**流程自動化是主角，AI 模型是它自動化處理的「判讀引擎」。**
兩層效益在 ROI 表分列、不混算。
            """
        )

        st.subheader("資料怎麼流")
        st.code(
            "NASA CMAPSS 真實感測資料\n"
            "      ↓\n"
            "[01] VAE 逐筆判讀健康狀態        → Accuracy 85.0% / Warning Recall 93.9%\n"
            "      ↓\n"
            f"   model_predictions.csv          {len(preds):,} 筆 Healthy / Warning\n"
            "      ↓  包裝成髒的每日 SAP-style 匯出檔\n"
            "[02] VBA：清理 → 去重 → 依機台彙總\n"
            "      ↓\n"
            "[03] Power Automate 自動寄報表   [05] Power BI 看板   [04] Power Apps 設計稿\n"
            "      ↓\n"
            "[06] ROI 效益驗證（實測🟢 / 假設🟡 分列）\n"
            "      ↓\n"
            "[07] 本網站：把上面每一步都變成你可以自己按的按鈕",
            language="text",
        )
        integrity_note(
            "模型的**判讀結果**是自動化流程的輸入。真實剩餘壽命（答案）只用來驗證模型準不準，"
            "不會出現在匯出檔裡 —— 因為現實中故障還沒發生，系統不可能知道答案。"
        )

    with right:
        st.subheader("怎麼讀這個網站")
        st.markdown(
            """
左側每一頁都對應履歷上的一句話，你可以直接跳到最想質疑的那一句：

- **即時判讀** — 模型是不是真的在跑？自己拉感測器滑桿，或導入一批沒見過的新引擎
- **機隊軌跡** — 13,096 筆判讀長什麼樣？哪 2 台被漏判？
- **自動化** — 髒資料變乾淨，按一個鈕看它發生
- **AI 助理** — 用自然語言問維修手冊與工單
- **效益驗證** — 84% / 36% / ROI 怎麼算出來的，公式全部攤開
            """
        )

        st.subheader("誠信原則")
        st.markdown(
            """
全站只要出現數字，一定帶標記：

- 🟢 **實測** — 在真實資料上實際跑出來的
- 🟡 **情境假設** — 推估值，輸入可調、公式公開

公開資料集沒有真實成本資料，所以**維護成本降低 84%、停機時間降低 36% 一律標為情境假設**，
不講成實測。模型指標、自動化耗時、消除的錯誤筆數則都是實測值。
            """
        )
        integrity_note(
            "本案的 SAP 匯出檔是**模擬**的（格式仿 SAP 匯出的髒檔），"
            "專案內未串接真實 SAP 系統。"
        )
        st.link_button("在 GitHub 上看完整原始碼", GITHUB, width="stretch")

    st.divider()

    with st.expander("English summary"):
        st.markdown(
            f"""
**Predictive Maintenance → Lean Operations Automation**

A VAE-based fault-detection model on NASA CMAPSS turbofan sensor data, extended into an
end-to-end DMAIC lean-automation case. The model scores every sensor reading as
*Healthy* or *Warning*; that output then feeds a fully automated reporting pipeline
(VBA macro → Power Automate Desktop → Power BI), replacing a manual
download-clean-summarise-email routine.

**Measured results 🟢**

- Accuracy **{v.accuracy:.1%}** over {v.n_engines} engines (last cycle each, standard CMAPSS protocol)
- Warning recall **{v.warning_recall:.1%}** — {v.cm[1,1]} of {v.cm[1].sum()} degrading engines caught,
  **{v.missed} missed**; {v.false_alarms} false alarms. The model is deliberately tuned to
  prefer a false alarm over a missed failure.
- Data processing **~500× faster** — 13,750 raw rows, 15 min manual → 1.6–1.8 s automated
  (two measured runs: 562× interactive, 488× via Power Automate)
- **2,001** silently miscounted rows eliminated (inconsistent status casing)

**Scenario assumptions 🟡**

- Maintenance cost −84%, downtime −36%, first-year ROI ≈200%, ~120 labour-hours saved per year.
  Public datasets carry no real cost data, so these are transparent projections —
  every input is adjustable on the *效益驗證* page.

Stack: Python · NumPy · VAE (PyTorch, exported to NumPy for deployment) ·
VBA · Power Automate Desktop · Power BI · RAG + Gemini API · Lean/Six Sigma (DMAIC)
            """
        )
