"""AI 助理：用自然語言查詢維修手冊、SOP、工單與交接紀錄（RAG）。"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.assistant import (
    KIND_LABEL, MAX_CHARS, MAX_QUESTIONS, SUGGESTED, SYSTEM_PROMPT, TOP_K,
    answer, cached_answer, load_faq, pretty_citations,
)
from core.llm import EMBED_DIM, EMBED_MODEL, get_api_key
from core.retrieval import CORPUS_DIR, Retriever
from core.ui import MEASURED, integrity_note, metric_card, page_header

HISTORY_KEY = "assistant_history"
COUNT_KEY = "assistant_count"
PENDING_KEY = "assistant_pending"

DOC_ORDER = ["manual", "sop", "work_orders", "shift_logs", "model_card", "lean"]


@st.cache_resource
def _retriever() -> Retriever:
    return Retriever()


@st.cache_data
def _faq() -> dict:
    return load_faq()


@st.cache_data
def _eval() -> dict | None:
    p = CORPUS_DIR / "rag_eval.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _ask(q: str) -> None:
    st.session_state[PENDING_KEY] = q


# ---------------------------------------------------------------------------
# 回答呈現
# ---------------------------------------------------------------------------

def _render_answer(a) -> None:
    if a.mode in ("generated", "cached"):
        st.markdown(pretty_citations(a.text), unsafe_allow_html=True)
        if a.invalid_citations:
            st.error("⚠️ 回答引用了不在檢索結果中的出處："
                     + "、".join(a.invalid_citations) + "。這部分內容可能不可靠。")
    if a.note:
        st.caption(("ℹ️ " if a.mode != "retrieval_only" else "⚠️ ") + a.note)

    how = "語意向量 + 代號比對" if a.retrieval in ("vector_id", "hybrid") else "關鍵字檢索（BM25，降級模式）"
    meta = [how, f"前 {len(a.hits)} 段"]
    if a.model:
        meta.append(f"生成模型 {a.model}")
    if a.seconds:
        meta.append(f"{a.seconds:.1f} 秒")

    expanded = a.mode == "retrieval_only"
    with st.expander("檢索到的段落　·　" + "　·　".join(meta), expanded=expanded):
        for n, h in enumerate(a.hits, start=1):
            c = h.chunk
            ranks = []
            if h.bm25_rank is not None:
                ranks.append(f"關鍵字第 {h.bm25_rank + 1} 名")
            if h.vector_rank is not None:
                ranks.append(f"語意第 {h.vector_rank + 1} 名")
            cited = "　📌 回答有引用" if c["id"] in a.cited else ""
            st.markdown(f"**{n}. `{c['id']}`　{c['doc_title']}｜{c['section']}**{cited}")
            st.caption(f"{KIND_LABEL[c['kind']]}　·　" + ("、".join(ranks) or "—"))
            st.text(c["text"])
            st.caption(f"來源：{c['source']}")


# ---------------------------------------------------------------------------
# 分頁
# ---------------------------------------------------------------------------

def _chat_tab(R: Retriever, key: str | None) -> None:
    history = st.session_state.setdefault(HISTORY_KEY, [])
    used = st.session_state.setdefault(COUNT_KEY, 0)
    faq = _faq()

    st.markdown("**試試這些問題**（預先產生的回答，不消耗即時額度）")
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTED):
        cols[i % 2].button(q, key=f"sugg_{i}", width="stretch", on_click=_ask, args=(q,))

    if history and st.button("清除對話", type="tertiary"):
        st.session_state[HISTORY_KEY] = []
        st.rerun()

    for a in history:
        with st.chat_message("user"):
            st.markdown(a.question)
        with st.chat_message("assistant"):
            _render_answer(a)

    remaining = MAX_QUESTIONS - used
    typed = st.chat_input(
        f"用中文問維修手冊、SOP、工單或交接紀錄（還可問 {remaining} 題）" if remaining > 0
        else "本次瀏覽的提問次數已用完，重新整理頁面即可重置",
        max_chars=MAX_CHARS, disabled=remaining <= 0,
    )
    question = st.session_state.pop(PENDING_KEY, None) or typed
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        a = cached_answer(R, question, faq)
        if a is None:
            if remaining <= 0:
                st.warning("本次瀏覽的提問次數已用完。")
                return
            with st.spinner("檢索文件、生成回答中…"):
                a = answer(R, question, key)
            # 只有真的生成出回答才扣次數；服務忙碌退回原文段落時不扣
            if a.mode == "generated":
                st.session_state[COUNT_KEY] = used + 1
    # 寫入歷史後重畫，讓剩餘題數與對話紀錄一起正確更新
    history.append(a)
    st.rerun()


def _docs_tab(R: Retriever) -> None:
    titles = {c["doc"]: (c["doc_title"], c["kind"]) for c in R.chunks}
    counts = pd.Series([c["doc"] for c in R.chunks]).value_counts()
    rows = [{"文件": titles[d][0], "性質": KIND_LABEL[titles[d][1]], "片段數": int(counts[d])}
            for d in DOC_ORDER if d in titles]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    doc = st.selectbox("閱讀全文", [d for d in DOC_ORDER if d in titles],
                       format_func=lambda d: titles[d][0])
    path = CORPUS_DIR / "docs" / f"{doc}.md"
    if doc == "work_orders":
        st.caption(f"工單共 {int(counts[doc])} 段，以下顯示全文（可捲動）。")
    with st.container(height=520, border=True):
        st.markdown(path.read_text(encoding="utf-8"))


def _how_tab(R: Retriever, key: str | None) -> None:
    st.markdown(f"""
#### 一個問題進來之後發生什麼事

1. **代號正規化**：`eng 64`、`ENG64`、`eng-64` 統一成 `ENG-064`
2. **語意檢索**：問題送 `{EMBED_MODEL}` 轉成 {EMBED_DIM} 維向量，與預先算好的 {len(R.chunks)} 個段落向量比餘弦相似度
3. **代號比對**：問題若提到機台代號，含該代號的段落優先排前面（純向量會把 ENG-006 和 ENG-056 搞混）
4. **取前 {TOP_K} 段**，與問題依下方 system prompt 組成提示，交給 Gemini 回答
5. **出處驗證**：程式檢查回答引用的每個 `[片段編號]` 是否真的在檢索結果中，捏造的出處會標紅

#### 設計取捨
- **段落向量離線算好**、隨 repo 部署；線上每題只呼叫一次 embedding，執行期幾乎零負擔
- **為什麼不用混合檢索**：原本預期 BM25 + 向量合併會最好，評估結果不是（見下表）—— BM25 在這份語料上雜訊太多，合併後反而拉低排序
- **降級路徑**：embedding 失敗 → 改用 BM25 關鍵字檢索；生成失敗 → 換下一個模型，全部失敗則直接列出原文段落。網頁不會因為 API 額度用完而壞掉
- **防濫用**：每次瀏覽最多 {MAX_QUESTIONS} 題、每題 {MAX_CHARS} 字；建議問題使用預先產生的回答
- **不裝額外套件**：Gemini 以標準庫 `urllib` 呼叫 REST API；中文斷詞不依賴 jieba
""")

    ev = _eval()
    if ev:
        st.markdown(f"#### 檢索品質評估（{ev['n_questions']} 題，🟢 實測）")
        names = {"bm25": "關鍵字（BM25）", "vector": "語意向量", "hybrid": "混合（BM25 + 向量，RRF）",
                 "vector_id": "語意向量 + 代號比對 ← 線上使用"}
        table = pd.DataFrame([{
            "檢索方式": names[m], "Hit@1": f"{ev[m].get('hit@1', 0):.1%}", "Hit@3": f"{ev[m]['hit@3']:.1%}",
            "Hit@5": f"{ev[m]['hit@5']:.1%}", "MRR": f"{ev[m]['mrr']:.3f}",
        } for m in ["bm25", "vector", "hybrid", "vector_id"] if m in ev])
        st.dataframe(table, hide_index=True, width="stretch")
        kinds = ev.get("kinds", {})
        st.caption(
            "題型：" + "、".join(f"{k} {n} 題" for k, n in kinds.items()) + "。"
            "Hit@1 = 第一名就是正確段落（生成模型最依賴第一名，最貼近回答品質）；"
            "Hit@3 = 前三名中至少一段正確。每題的正確段落依內容事先訂定，未依檢索結果回頭調整。"
        )
        st.caption(
            "⚠️ 限制：「機台代號」12 題是在發現純向量會混淆 ENG-006 / ENG-056 之後才加入題庫，"
            "代號比對規則也是看到這個問題才設計的，因此這 12 題對「語意向量 + 代號比對」不算獨立驗證。"
            "題庫共 36 題，規模小，名次差 1–2 題即會影響百分比。"
        )

    st.markdown("#### System prompt（Prompt Engineering）")
    st.code(SYSTEM_PROMPT, language="markdown")


# ---------------------------------------------------------------------------
# 頁面
# ---------------------------------------------------------------------------

def render() -> None:
    page_header(
        "AI 助理",
        "用自然語言查詢這個機隊的維修手冊、異常處置 SOP、維修工單與交接班紀錄。"
        "回答只根據檢索到的文件段落，每一句都標出處，查不到就說查不到。",
        "built an AI chatbot that answers anomaly questions in natural language, "
        "powered by RAG and an LLM API",
    )

    R = _retriever()
    key = get_api_key()
    ev = _eval()
    n_docs = len({c["doc"] for c in R.chunks})
    n_sim = sum(1 for c in R.chunks if c["kind"] == "simulated")

    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("文件庫", f"{len(R.chunks)} 段",
                    f"{n_docs} 份文件；其中 {n_sim} 段為模擬現場文件", None)
    with c2:
        if ev and "vector_id" in ev:
            metric_card("檢索第一名命中率", f"{ev['vector_id']['hit@1']:.0%}",
                        f"{ev['n_questions']} 題評估；只用關鍵字為 {ev['bm25']['hit@1']:.0%}", MEASURED)
        elif ev:
            metric_card("檢索命中率 Hit@3", f"{ev['bm25']['hit@3']:.0%}",
                        "關鍵字檢索（向量索引尚未建立）", MEASURED)
    with c3:
        if key and R.has_vectors:
            status, note = "語意檢索 + 生成", "gemini-embedding-2 + Gemini（BM25 為降級備援）"
        elif key:
            status, note = "關鍵字檢索 + 生成", "向量索引尚未建立"
        else:
            status, note = "僅檢索", "未設定 API 金鑰，直接顯示原文段落"
        metric_card("目前模式", status, note, None)

    integrity_note(
        "文件庫中的維修手冊、SOP、工單、交接紀錄為**模擬文件**（NASA CMAPSS 沒有這類資料），"
        "但其中出現的引擎編號、cycle、判讀結果、感測器範圍全部由真實資料計算；"
        "模型卡與精實改善文件為本專案真實文件。模擬文件不含真實剩餘壽命 —— 現場不可能事先知道答案。"
    )

    t1, t2, t3 = st.tabs(["對話", "文件庫", "系統怎麼運作"])
    with t1:
        _chat_tab(R, key)
    with t2:
        _docs_tab(R)
    with t3:
        _how_tab(R, key)
