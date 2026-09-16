"""共用的版面元件與誠信標註。

誠信標註原則（沿用 06-lean-lss/roi-validation.xlsx 的慣例）：
    🟢 實測 —— 在真實資料上實際跑出來的數字
    🟡 假設 —— 情境假設或推估值，輸入可調、公式公開
全站只要出現數字，就必須帶其中一種標記。
"""

from __future__ import annotations

import streamlit as st

MEASURED = "measured"
ASSUMED = "assumed"

_BADGE = {
    MEASURED: ("🟢", "實測", "#0f7b34"),
    ASSUMED: ("🟡", "情境假設", "#a06a00"),
}

CSS = """
<style>
  .pm-badge {
      display:inline-block; font-size:.72rem; font-weight:600;
      padding:.1rem .45rem; border-radius:.35rem; margin-left:.35rem;
      border:1px solid currentColor; opacity:.9; white-space:nowrap;
  }
  .pm-card {
      border:1px solid rgba(128,128,128,.25); border-radius:.6rem;
      padding:.85rem 1rem; height:100%;
  }
  .pm-card .pm-label { font-size:.8rem; opacity:.75; }
  .pm-card .pm-value { font-size:1.7rem; font-weight:700; line-height:1.25; }
  .pm-card .pm-note  { font-size:.75rem; opacity:.65; margin-top:.15rem; }
  .pm-lede { font-size:1.02rem; line-height:1.7; opacity:.9; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge_html(kind: str) -> str:
    icon, text, colour = _BADGE[kind]
    return f'<span class="pm-badge" style="color:{colour}">{icon} {text}</span>'


def metric_card(label: str, value: str, note: str = "", kind: str | None = MEASURED) -> None:
    """kind=None 表示這張卡片不是量測或推估的數字（例如狀態、數量），不加誠信標記。"""
    badge = badge_html(kind) if kind else ""
    st.markdown(
        f"""<div class="pm-card">
              <div class="pm-label">{label}{badge}</div>
              <div class="pm-value">{value}</div>
              <div class="pm-note">{note}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def page_header(title: str, lede: str, claim: str | None = None) -> None:
    """每頁開頭：標題、一句話說明，以及這頁對應履歷的哪一句主張。"""
    st.title(title)
    st.markdown(f'<p class="pm-lede">{lede}</p>', unsafe_allow_html=True)
    if claim:
        st.caption(f"對應履歷主張：{claim}")
    st.divider()


def integrity_note(text: str) -> None:
    st.caption(f"ℹ️ {text}")
