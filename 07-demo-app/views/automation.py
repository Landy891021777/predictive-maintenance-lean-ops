"""自動化（P2 建置中）。"""

from __future__ import annotations

import streamlit as st

from core.ui import page_header


def render() -> None:
    page_header("自動化", "這一頁屬於 P2 階段，尚未建置。")
    st.info("🚧 P2 建置中。目前可用的是「總覽」「即時判讀」「機隊軌跡」三頁。")
