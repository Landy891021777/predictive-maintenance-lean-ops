"""
預先產生建議問題的回答，存成 faq_answers.json。

網頁上點「建議問題」時直接顯示這些回答，不即時呼叫 API：
面試當天就算免費層額度用完，最常被點的幾題仍然能正常展示。
回答以與線上完全相同的流程產生（檢索 → prompt → 生成 → 出處驗證）。

執行：py -3 07-demo-app/build/build_faq.py
需要：.streamlit/secrets.toml 內的 GEMINI_API_KEY，以及已建立的 embeddings.npz
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.assistant import FAQ_PATH, SUGGESTED, answer  # noqa: E402
from core.llm import get_api_key  # noqa: E402
from core.retrieval import Retriever  # noqa: E402


def main() -> int:
    key = get_api_key()
    if not key:
        print("❌ 找不到金鑰")
        return 1
    R = Retriever()
    if not R.has_vectors:
        print("❌ 尚未建立 embeddings.npz，請先執行 embed_corpus.py")
        return 1

    out, ok = [], True
    for q in SUGGESTED:
        a = answer(R, q, key)
        if a.mode != "generated":                  # 暫時性錯誤：等 30 秒再試一次
            print(f"⏳ 第一次失敗（{a.note}），30 秒後重試")
            time.sleep(30)
            a = answer(R, q, key)
        if a.mode != "generated":
            print(f"❌ 無法生成：{q}｜{a.note}")
            return 1
        flag = "✅" if not a.invalid_citations else "⚠️"
        ok &= not a.invalid_citations
        print(f"{flag} {a.seconds:4.1f}s {a.model}｜{q}")
        print(f"   檢索 {a.retrieval}：{[h.chunk['id'] for h in a.hits]}")
        print(f"   引用 {a.cited}" + (f"｜不在檢索結果中的引用 {a.invalid_citations}" if a.invalid_citations else ""))
        print("   " + a.text.replace("\n", "\n   ") + "\n")
        out.append({
            "question": q, "text": a.text, "model": a.model, "retrieval": a.retrieval,
            "hit_ids": [h.chunk["id"] for h in a.hits],
            "bm25_ranks": [h.bm25_rank for h in a.hits],
            "vector_ranks": [h.vector_rank for h in a.hits],
            "cited": a.cited, "invalid_citations": a.invalid_citations,
        })
        time.sleep(4)                      # 免費層每分鐘請求數有限，放慢一點

    FAQ_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已寫入 {FAQ_PATH.name}，共 {len(out)} 題")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
