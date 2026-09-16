"""
檢查 Gemini 金鑰與免費層可用的模型。不會印出金鑰。

  1. 確認找得到金鑰
  2. 列出這把金鑰可見的生成模型與 embedding 模型
  3. 對候選生成模型各送一個極短的請求，確認免費層實際能不能用、要多久
  4. 確認 embedding 模型可用、維度正確

執行：py -3 07-demo-app/build/probe_gemini.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.llm import EMBED_DIM, EMBED_MODEL, GeminiError, embed_query, generate, get_api_key, list_models  # noqa: E402

# 由輕到重；免費層通常只開放部分模型，實測為準
CANDIDATES = [
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash",
    "gemini-3.6-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash",
]


def main() -> int:
    key = get_api_key()
    if not key:
        print("❌ 找不到金鑰。請在 .streamlit/secrets.toml 填入 GEMINI_API_KEY。")
        return 1
    print("✅ 已找到金鑰（不顯示內容）")

    try:
        models = list_models(key)
    except GeminiError as e:
        print(f"❌ 無法列出模型：{e}")
        return 1
    gen = sorted(m["name"].split("/")[-1] for m in models
                 if "generateContent" in m.get("supportedGenerationMethods", []))
    emb = sorted(m["name"].split("/")[-1] for m in models
                 if "embedContent" in m.get("supportedGenerationMethods", []))
    print(f"\n可見的生成模型 {len(gen)} 個（節錄 flash 系列）：")
    print("  " + ", ".join(g for g in gen if "flash" in g))
    print(f"可見的 embedding 模型：{', '.join(emb)}")

    print("\n實測候選生成模型：")
    usable = []
    for m in CANDIDATES:
        if m not in gen:
            print(f"  {m:24s} 不在清單中")
            continue
        t0 = time.perf_counter()
        try:
            text, meta = generate(m, "你是測試助理。", "只回答兩個字：正常", key, max_tokens=512)
            dt = time.perf_counter() - t0
            print(f"  {m:24s} ✅ {dt:.1f} 秒，回覆「{text[:10]}」，結束原因 {meta['finish_reason']}")
            usable.append(m)
        except GeminiError as e:
            print(f"  {m:24s} ❌ {e.status} {e.message[:80]}")

    print("\nEmbedding：")
    try:
        v = embed_query("引擎 ENG-064 目前的工單狀態？", key)
        print(f"  {EMBED_MODEL} ✅ 維度 {len(v)}（期望 {EMBED_DIM}）")
    except GeminiError as e:
        print(f"  {EMBED_MODEL} ❌ {e.status} {e.message[:80]}")
        return 1

    print(f"\n可用的生成模型：{usable or '無'}")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
