"""
離線向量化文件庫：對 chunks.json 每個片段呼叫 gemini-embedding-2，存成 embeddings.npz。

線上網站只載入這個檔案，執行期不需要對文件做任何 embedding；
只有使用者的問題才會即時向量化（每題一次 API 呼叫）。

文件格式依官方建議：title: {文件｜章節} | text: {內文}

執行：py -3 07-demo-app/build/embed_corpus.py
需要：.streamlit/secrets.toml 內的 GEMINI_API_KEY
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.llm import EMBED_DIM, EMBED_MODEL, GeminiError, embed_batch, format_document, get_api_key  # noqa: E402
from core.retrieval import CORPUS_DIR  # noqa: E402


def main() -> int:
    key = get_api_key()
    if not key:
        print("❌ 找不到金鑰，請先在 .streamlit/secrets.toml 填入 GEMINI_API_KEY")
        return 1

    chunks = json.loads((CORPUS_DIR / "chunks.json").read_text(encoding="utf-8"))
    texts = [format_document(f"{c['doc_title']}｜{c['section']}", c["text"]) for c in chunks]

    t0 = time.perf_counter()
    for attempt in range(1, 4):
        try:
            vectors = embed_batch(texts, key, batch_size=50, pause=2.0)
            break
        except GeminiError as e:
            if e.rate_limited and attempt < 3:
                print(f"⚠️ 觸發頻率限制，{20 * attempt} 秒後重試（第 {attempt} 次）")
                time.sleep(20 * attempt)
                continue
            print(f"❌ 向量化失敗：{e}")
            return 1

    v = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(v, axis=1)
    np.savez_compressed(
        CORPUS_DIR / "embeddings.npz",
        ids=np.array([c["id"] for c in chunks]),
        vectors=v,
        model=np.array(EMBED_MODEL),
        dim=np.array(EMBED_DIM),
    )
    size = (CORPUS_DIR / "embeddings.npz").stat().st_size / 1024
    print(f"✅ {len(chunks)} 個片段 × {v.shape[1]} 維，耗時 {time.perf_counter() - t0:.1f} 秒")
    print(f"   向量長度 {norms.min():.4f} – {norms.max():.4f}（應接近 1）")
    print(f"   embeddings.npz {size:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
