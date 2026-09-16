"""
Gemini API 的最小 REST 客戶端（只用標準庫 urllib，不需安裝 SDK）。

金鑰讀取順序：
  1. st.secrets["GEMINI_API_KEY"]   —— Streamlit Cloud 後台 Secrets，或本機以 repo 根目錄為工作目錄啟動時
  2. 環境變數 GEMINI_API_KEY
  3. <repo>/.streamlit/secrets.toml  —— 本機從其他工作目錄啟動時的後備（此檔已列入 .gitignore）

安全設計：金鑰只放在 x-goog-api-key 標頭，不放進網址；例外訊息只帶 HTTP 狀態與 API 回傳的錯誤說明，
永遠不包含金鑰。

API 格式依 Google 官方文件（2026-09 查證）：
  - gemini-embedding-2 不支援 task_type，改在文字前加前綴：
      查詢：task: question answering | query: {text}
      文件：title: {title} | text: {text}
  - output_dimensionality=768 時模型會自動正規化
"""

from __future__ import annotations

import json
import os
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768
TIMEOUT = 45

REPO_ROOT = Path(__file__).resolve().parents[2]


class GeminiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message

    @property
    def rate_limited(self) -> bool:
        return self.status == 429


# ---------------------------------------------------------------------------
# 金鑰
# ---------------------------------------------------------------------------

def get_api_key() -> str | None:
    try:
        import streamlit as st

        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return str(key).strip()
    except Exception:  # 沒有 secrets 檔時 st.secrets 會拋例外
        pass

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    path = REPO_ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        try:
            key = str(tomllib.loads(path.read_text(encoding="utf-8")).get("GEMINI_API_KEY", "")).strip()
        except tomllib.TOMLDecodeError:
            return None
        return key or None
    return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _request(method: str, path: str, key: str, body: dict | None = None,
             timeout: float = TIMEOUT) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise GeminiError(e.code, msg or e.reason) from None
    except urllib.error.URLError as e:
        raise GeminiError(0, f"連線失敗：{e.reason}") from None
    except (TimeoutError, OSError, ValueError) as e:
        # 讀取回應時逾時丟的是 TimeoutError，不會被包成 URLError；連線被重置、SSL 中斷則是 OSError。
        # 沒攔的話整個頁面會噴出例外，而不是換下一個模型。
        raise GeminiError(0, f"連線逾時或中斷：{type(e).__name__}") from None


def list_models(key: str) -> list[dict]:
    out, token = [], None
    while True:
        q = "models?pageSize=100" + (f"&pageToken={token}" if token else "")
        r = _request("GET", q, key)
        out += r.get("models", [])
        token = r.get("nextPageToken")
        if not token:
            return out


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def format_query(text: str) -> str:
    return f"task: question answering | query: {text}"


def format_document(title: str, text: str) -> str:
    return f"title: {title} | text: {text}"


def embed_batch(texts: list[str], key: str, batch_size: int = 50,
                pause: float = 0.0) -> list[list[float]]:
    """批次 embedding；每一段文字各自回傳一個向量。"""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        body = {"requests": [
            {"model": f"models/{EMBED_MODEL}",
             "content": {"parts": [{"text": t}]},
             "output_dimensionality": EMBED_DIM}
            for t in texts[i:i + batch_size]
        ]}
        r = _request("POST", f"models/{EMBED_MODEL}:batchEmbedContents", key, body)
        vectors += [e["values"] for e in r["embeddings"]]
        if pause and i + batch_size < len(texts):
            time.sleep(pause)
    return vectors


def embed_query(text: str, key: str) -> list[float]:
    body = {"content": {"parts": [{"text": format_query(text)}]},
            "output_dimensionality": EMBED_DIM}
    r = _request("POST", f"models/{EMBED_MODEL}:embedContent", key, body)
    return r["embedding"]["values"]


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def generate(model: str, system: str, prompt: str, key: str,
             temperature: float = 0.2, max_tokens: int = 2048,
             timeout: float = TIMEOUT) -> tuple[str, dict]:
    """回傳 (文字, 中繼資訊)。中繼資訊含 finishReason 與 token 用量，供除錯與頁面顯示。"""
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    r = _request("POST", f"models/{model}:generateContent", key, body, timeout=timeout)
    cands = r.get("candidates") or []
    if not cands:
        reason = r.get("promptFeedback", {}).get("blockReason", "無回應內容")
        raise GeminiError(200, f"模型未產生回答（{reason}）")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    meta = {"finish_reason": cands[0].get("finishReason"), "usage": r.get("usageMetadata", {})}
    return text.strip(), meta
