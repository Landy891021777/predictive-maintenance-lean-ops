"""
RAG 檢索評估：比較 BM25、向量、混合（RRF）三種檢索方式。

=== 題庫設計原則 ===
- 每題的正確答案（gold）依「哪個段落真的含有答案」事先訂定，不看檢索結果回頭調整
- 刻意混合三種問法：
    精確代號型（ENG-064、Sensor 4）          —— 關鍵字檢索的強項
    換句話說型（不使用文件原字詞）            —— 語意向量的強項
    概念型（為什麼、怎麼算）
- gold 以（文件, 章節開頭）或（文件, 涉及引擎）指定，片段 id 變動時不會失效

指標：
  Hit@3 / Hit@5  前 k 名中是否至少有一個正確段落
  MRR            第一個正確段落排名的倒數平均

輸出：07-demo-app/assets/corpus/rag_eval.json（網頁 AI 助理頁顯示的實測指標）

執行：py -3 07-demo-app/build/rag_eval.py
      （沒有 embeddings.npz 或沒有金鑰時，只評估 BM25）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from core.llm import GeminiError, embed_batch, format_query, get_api_key  # noqa: E402
from core.retrieval import CORPUS_DIR, Retriever  # noqa: E402

# (問題, 問法類型, [gold 條件...])；gold 條件：("sec", 文件, 章節開頭) 或 ("eng", 文件, 引擎, 章節開頭)
QUESTIONS = [
    ("ENG-064 的工單現在是什麼狀態？", "精確代號", [("eng", "work_orders", "ENG-064", "MWO"), ("sec", "shift_logs", "特記事項 ENG-064")]),
    ("72 號引擎最後一筆讀數是健康的，可以結案嗎？", "換句話說", [("sec", "shift_logs", "特記事項 ENG-072"), ("eng", "work_orders", "ENG-072", "MWO")]),
    ("Sensor 4 的正常範圍是多少？", "精確代號", [("sec", "manual", "2.1")]),
    ("高壓壓縮機出口的靜壓是由哪一顆感測器量測？", "換句話說", [("sec", "manual", "2.2")]),
    ("L3 停機檢查要在多久內處理完？", "精確代號", [("sec", "sop", "4.")]),
    ("排程檢查的時限是幾小時？", "換句話說", [("sec", "sop", "3.")]),
    ("什麼情況下要把引擎停下來檢查？", "換句話說", [("sec", "sop", "1."), ("sec", "sop", "4.")]),
    ("哪些感測器讀數一直不變、不用看？", "換句話說", [("sec", "manual", "2.5")]),
    ("壓縮機快壞的時候，溫度會往哪個方向變？", "換句話說", [("sec", "manual", "2.6"), ("sec", "manual", "2.1")]),
    ("模型的準確率和召回率是多少？", "概念", [("sec", "model_card", "4.")]),
    ("模型有哪些引擎沒抓到？", "換句話說", [("sec", "model_card", "5.")]),
    ("系統是怎麼決定一筆讀數是 Healthy 還是 Warning？", "概念", [("sec", "manual", "3."), ("sec", "model_card", "2.")]),
    ("為什麼不直接訓練一個分類器？", "概念", [("sec", "model_card", "1.")]),
    ("維護成本降低 84% 是怎麼算出來的？", "精確代號", [("sec", "lean", "6.")]),
    ("自動化之後比人工快了幾倍？", "換句話說", [("sec", "lean", "3.")]),
    ("用 Excel 手動整理報表可能會有什麼看不出來的錯？", "換句話說", [("sec", "lean", "4.")]),
    ("這個改善案多久可以回本？", "換句話說", [("sec", "lean", "5.")]),
    ("專案有沒有真的連到 SAP 系統？", "概念", [("sec", "lean", "7.")]),
    ("總共開了幾張維修工單？", "換句話說", [("sec", "work_orders", "工單總覽")]),
    ("哪些引擎從來沒有開過工單？", "換句話說", [("sec", "work_orders", "未開立工單")]),
    ("多久要做一次例行巡檢？", "換句話說", [("sec", "manual", "4.")]),
    ("這個模型在什麼條件下沒有驗證過？", "概念", [("sec", "model_card", "7.")]),
    ("7 月 1 日日班交接了哪些事？", "精確代號", [("sec", "shift_logs", "2026-07-01 日班")]),
    ("只看最後一筆讀數和看一段時間的趨勢，哪個比較不會漏掉壞掉的引擎？", "換句話說", [("sec", "model_card", "6."), ("sec", "sop", "5.")]),
]

QUERY_CACHE = CORPUS_DIR / "eval_query_vectors.npz"


def gold_ids(chunks: list[dict], conds: list[tuple]) -> set[str]:
    ids = set()
    for cond in conds:
        if cond[0] == "sec":
            _, doc, prefix = cond
            ids |= {c["id"] for c in chunks if c["doc"] == doc and c["section"].startswith(prefix)}
        else:
            _, doc, engine, prefix = cond
            ids |= {c["id"] for c in chunks
                    if c["doc"] == doc and engine in c["engines"] and c["section"].startswith(prefix)}
    return ids


def query_vectors(key: str | None) -> np.ndarray | None:
    qs = [q for q, _, _ in QUESTIONS]
    if QUERY_CACHE.exists():
        c = np.load(QUERY_CACHE, allow_pickle=False)
        if list(c["questions"]) == qs:
            return c["vectors"]
    if not key:
        return None
    try:
        vecs = np.asarray(embed_batch([format_query(q) for q in qs], key), dtype=np.float32)
    except GeminiError as e:
        print(f"⚠️ 問題向量化失敗，只評估 BM25：{e}")
        return None
    np.savez_compressed(QUERY_CACHE, questions=np.array(qs), vectors=vecs)
    return vecs


def evaluate(R: Retriever, mode: str, qvecs: np.ndarray | None) -> dict:
    hits3 = hits5 = 0
    rr = []
    per_q = []
    for i, (q, kind, conds) in enumerate(QUESTIONS):
        gold = gold_ids(R.chunks, conds)
        assert gold, f"題目「{q}」找不到 gold 段落，請檢查條件"
        if mode == "bm25":
            ranked = R.search(q, k=len(R.chunks))
        elif mode == "vector":
            v = qvecs[i] / np.linalg.norm(qvecs[i])
            order = np.argsort(-(R.vectors @ v))
            ranked = [type("H", (), {"chunk": R.chunks[j]}) for j in order]
        else:
            ranked = R.search(q, k=len(R.chunks), query_vector=qvecs[i].tolist())
        ids = [h.chunk["id"] for h in ranked]
        first = next((r for r, cid in enumerate(ids, start=1) if cid in gold), None)
        hits3 += bool(first and first <= 3)
        hits5 += bool(first and first <= 5)
        rr.append(1.0 / first if first else 0.0)
        per_q.append({"q": q, "kind": kind, "rank": first, "top3": ids[:3], "gold": sorted(gold)})
    n = len(QUESTIONS)
    return {"hit@3": hits3 / n, "hit@5": hits5 / n, "mrr": float(np.mean(rr)), "per_question": per_q}


def main() -> int:
    R = Retriever()
    key = get_api_key()
    qvecs = query_vectors(key) if R.has_vectors else None

    modes = ["bm25"] + (["vector", "hybrid"] if qvecs is not None else [])
    results = {m: evaluate(R, m, qvecs) for m in modes}

    print(f"題數 {len(QUESTIONS)}（" + "、".join(
        f"{k} {sum(1 for _, t, _ in QUESTIONS if t == k)}" for k in ["精確代號", "換句話說", "概念"]) + "）\n")
    print(f"{'檢索方式':10s} {'Hit@3':>7s} {'Hit@5':>7s} {'MRR':>7s}")
    for m, r in results.items():
        print(f"{m:12s} {r['hit@3']:7.1%} {r['hit@5']:7.1%} {r['mrr']:7.3f}")

    for kind in ["精確代號", "換句話說", "概念"]:
        row = [kind]
        for m, r in results.items():
            qs = [p for p in r["per_question"] if p["kind"] == kind]
            row.append(f"{m} {sum(1 for p in qs if p['rank'] and p['rank'] <= 3)}/{len(qs)}")
        print("  Hit@3 依問法：" + "｜".join(row))

    worst = results[modes[-1]]["per_question"]
    misses = [p for p in worst if not p["rank"] or p["rank"] > 3]
    if misses:
        print(f"\n{modes[-1]} 前三名沒命中的題目：")
        for p in misses:
            print(f"  排名 {p['rank']}｜{p['q']}｜前三名 {p['top3']}｜正確 {p['gold']}")

    out = {m: {k: v for k, v in r.items()} for m, r in results.items()}
    out["n_questions"] = len(QUESTIONS)
    (CORPUS_DIR / "rag_eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
