"""
混合檢索：BM25 關鍵字檢索 + 向量檢索，以 Reciprocal Rank Fusion（RRF）合併排序。

=== 為什麼這樣設計 ===
- 向量已在建置時離線算好（assets/corpus/embeddings.npz），線上只對「使用者的問題」
  呼叫一次 embedding API，執行期幾乎沒有負擔。
- BM25 同時參與排序：機台代號（ENG-064）、工單號（MWO-2026-0045）、感測器編號
  這類精確字串，關鍵字比對比語意向量可靠。
- 降級路徑：embedding API 失敗（額度用完、斷線）時自動只用 BM25，網頁不會壞。

=== 中文斷詞 ===
不裝 jieba。中文取「字元二元組」（引擎健康 → 引擎、擎健、健康），
英數保留完整詞並轉小寫（ENG-064 → eng-064；另拆出 064 以便只打數字也查得到）。
零依賴，且對代號類查詢比分詞器穩定。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CORPUS_DIR = Path(__file__).resolve().parent.parent / "assets" / "corpus"

_CJK = re.compile(r"[一-鿿]+")
_ASCII = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*")
_ENG = re.compile(r"\beng[\s\-_]?0*(\d{1,3})\b", re.I)


def normalize_engine_ids(text: str) -> str:
    """把 eng 64、ENG64、eng-64 統一成 ENG-064，讓使用者隨手打也查得到。"""
    return _ENG.sub(lambda m: f"ENG-{int(m.group(1)):03d}", text)


def tokenize(text: str) -> list[str]:
    text = normalize_engine_ids(text)
    tokens: list[str] = []
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens += [run[i:i + 2] for i in range(len(run) - 1)]
    for word in _ASCII.findall(text):
        w = word.lower().strip("._-")
        if not w:
            continue
        tokens.append(w)
        if "-" in w:                                   # eng-064 → 另拆出 064
            tokens += [p for p in w.split("-") if p.isdigit()]
    return tokens


@dataclass
class Hit:
    chunk: dict
    score: float
    bm25_rank: int | None
    vector_rank: int | None


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=float)
        self.avg = float(self.len.mean()) if len(docs) else 0.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.tf))
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(t)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                    out[i] += idf * f * (self.k1 + 1) / denom
        return out


class Retriever:
    def __init__(self, corpus_dir: Path = CORPUS_DIR):
        self.chunks: list[dict] = json.loads((corpus_dir / "chunks.json").read_text(encoding="utf-8"))
        self.bm25 = BM25([tokenize(self.index_text(c)) for c in self.chunks])

        emb_path = corpus_dir / "embeddings.npz"
        self.vectors: np.ndarray | None = None
        if emb_path.exists():
            e = np.load(emb_path, allow_pickle=False)
            if list(e["ids"]) == [c["id"] for c in self.chunks]:
                v = e["vectors"].astype(np.float32)
                self.vectors = v / np.linalg.norm(v, axis=1, keepdims=True)

    @staticmethod
    def index_text(c: dict) -> str:
        return f"{c['doc_title']} {c['section']} {c['text']}"

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None

    def search(self, query: str, k: int = 5, query_vector: list[float] | None = None,
               rrf_k: int = 60) -> list[Hit]:
        """query_vector 為 None 時只用 BM25（降級模式）。"""
        bm = self.bm25.scores(tokenize(query))
        bm_order = [i for i in np.argsort(-bm) if bm[i] > 0]
        bm_rank = {i: r for r, i in enumerate(bm_order)}

        vec_rank: dict[int, int] = {}
        if query_vector is not None and self.vectors is not None:
            q = np.asarray(query_vector, dtype=np.float32)
            q /= np.linalg.norm(q)
            sims = self.vectors @ q
            vec_rank = {i: r for r, i in enumerate(np.argsort(-sims))}

        fused: dict[int, float] = {}
        for i, r in bm_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + r + 1)
        for i, r in vec_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + r + 1)

        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [Hit(self.chunks[i], fused[i], bm_rank.get(i), vec_rank.get(i)) for i in top]
