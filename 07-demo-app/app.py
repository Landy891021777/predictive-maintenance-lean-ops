"""
預測維護 → 精實營運自動化：面試展示用互動網站。

執行（本機）：
    streamlit run 07-demo-app/app.py

部署（Streamlit Community Cloud）：
    Repository  Landy891021777/predictive-maintenance-lean-ops
    Branch      main
    Main file   07-demo-app/app.py

線上不需要 PyTorch —— VAE 權重已由 build/export_artifacts.py 匯出成 NumPy 陣列，
推論路徑經 build/verify_numpy_path.py 驗證可逐格重現 model_validation.md 的實測結果。
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.ui import inject_css  # noqa: E402
from views import assistant, automation, fleet, live_detection, overview, roi  # noqa: E402

st.set_page_config(
    page_title="預測維護 → 精實營運自動化",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# 每個 view 的進入點都叫 render()，所以必須明確指定 url_path，否則路由會撞名。
PAGES = [
    st.Page(overview.render, title="總覽", icon=":material/home:",
            url_path="overview", default=True),
    st.Page(live_detection.render, title="即時判讀", icon=":material/sensors:",
            url_path="live-detection"),
    st.Page(fleet.render, title="機隊軌跡", icon=":material/timeline:",
            url_path="fleet"),
    st.Page(automation.render, title="自動化", icon=":material/bolt:",
            url_path="automation"),
    st.Page(assistant.render, title="AI 助理", icon=":material/chat:",
            url_path="assistant"),
    st.Page(roi.render, title="效益驗證", icon=":material/calculate:",
            url_path="roi"),
]

with st.sidebar:
    st.markdown("### 黃茗琳 Landy Huang")
    st.caption("Predictive Maintenance & Anomaly Detection\n\nPython · RPA · RAG · Prompt Engineering")

st.navigation(PAGES).run()

with st.sidebar:
    st.divider()
    st.caption(
        "資料來源：NASA CMAPSS FD001（公開資料集）。\n\n"
        "本案的 SAP 匯出檔為模擬檔，未串接真實 SAP 系統。\n\n"
        "🟢 實測 ／ 🟡 情境假設"
    )
