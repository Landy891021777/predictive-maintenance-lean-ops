"""
資料載入與快取。

所有數字都從 repo 裡既有的產出檔讀取，不在這裡寫死，
這樣網頁顯示的內容必然與 01-core-model/outputs/ 的驗證結果一致。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_DIR.parent
ASSETS = APP_DIR / "assets"
OUTPUTS = REPO_ROOT / "01-core-model" / "outputs"


@dataclass(frozen=True)
class Validation:
    """model_validation.csv 算出來的實測指標（100 台引擎，最後一個 cycle）。"""

    n_engines: int
    accuracy: float
    cm: np.ndarray                 # [[HH, HW], [WH, WW]]
    healthy_precision: float
    healthy_recall: float
    warning_precision: float
    warning_recall: float

    @property
    def missed(self) -> int:
        """漏判：實際 Warning 卻被判 Healthy —— 代價最高的錯誤。"""
        return int(self.cm[1, 0])

    @property
    def false_alarms(self) -> int:
        """誤報：實際 Healthy 卻被判 Warning —— 代價較低（多做一次檢查）。"""
        return int(self.cm[0, 1])


@st.cache_resource
def get_detector():
    from core.model import VaeDetector

    return VaeDetector(ASSETS)


@st.cache_data
def load_meta() -> dict:
    return json.loads((ASSETS / "meta.json").read_text(encoding="utf-8"))


@st.cache_data
def load_predictions() -> pd.DataFrame:
    """13,096 筆逐筆判讀（模擬營運系統的每日輸出，不含真實 RUL 答案）。"""
    df = pd.read_csv(OUTPUTS / "model_predictions.csv", encoding="utf-8-sig")
    df["EquipmentID"] = df["unit_number"].map(lambda u: f"ENG-{u:03d}")
    return df


@st.cache_data
def load_validation() -> Validation:
    df = pd.read_csv(OUTPUTS / "model_validation.csv", encoding="utf-8-sig")
    truth, pred = df["TrueLabel"].values, df["PredictedStatus"].values
    cm = np.array([
        [int(((truth == "Healthy") & (pred == "Healthy")).sum()),
         int(((truth == "Healthy") & (pred == "Warning")).sum())],
        [int(((truth == "Warning") & (pred == "Healthy")).sum()),
         int(((truth == "Warning") & (pred == "Warning")).sum())],
    ])
    return Validation(
        n_engines=len(df),
        accuracy=float((truth == pred).mean()),
        cm=cm,
        healthy_precision=cm[0, 0] / cm[:, 0].sum(),
        healthy_recall=cm[0, 0] / cm[0].sum(),
        warning_precision=cm[1, 1] / cm[:, 1].sum(),
        warning_recall=cm[1, 1] / cm[1].sum(),
    )


@st.cache_data
def load_validation_table() -> pd.DataFrame:
    """每台引擎最後一個 cycle 的判讀 vs 真實答案（含 TrueRUL），用來找出漏判與誤報的機台。"""
    df = pd.read_csv(OUTPUTS / "model_validation.csv", encoding="utf-8-sig")
    df["結果"] = np.select(
        [
            (df["TrueLabel"] == "Warning") & (df["PredictedStatus"] == "Healthy"),
            (df["TrueLabel"] == "Healthy") & (df["PredictedStatus"] == "Warning"),
        ],
        ["漏判", "誤報"],
        default="判讀正確",
    )
    return df


@st.cache_data
def load_test_readings() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(unit, cycle, sensors[n, 21]) —— 即時判讀頁用來載入真實引擎的某個 cycle。"""
    r = np.load(ASSETS / "test_readings.npz")
    return r["unit"], r["cycle"], r["sensors"]


@st.cache_data
def load_support_scatter(max_points: int = 4000) -> pd.DataFrame:
    """support set 的潛空間散點（抽樣後供繪圖，避免畫 14,441 點拖慢瀏覽器）。"""
    sup = np.load(ASSETS / "support.npz")
    z, labels = sup["z"], sup["labels"]
    rng = np.random.default_rng(34)
    idx = rng.choice(len(z), size=min(max_points, len(z)), replace=False)
    return pd.DataFrame({
        "z1": z[idx, 0],
        "z2": z[idx, 1],
        "狀態": np.where(labels[idx] == 1, "Warning", "Healthy"),
    })
