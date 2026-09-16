"""
純 NumPy 的 VAE 推論。

線上不裝 PyTorch（見 build/export_artifacts.py 的說明），這裡用 assets/vae_weights.npz
重算 encoder / decoder。權重來自 vae_model.pth，匯出時已驗證與 PyTorch 逐筆一致
（最大絕對誤差 7.2e-07，純 float32 捨入）。

判讀規則與 01-core-model/scoring/score_engines.py 相同：
    原始感測值 → MinMaxScaler → encoder 取 mu → 在 support set 上找最近的點（1-NN）
    → 取該點的標籤（Healthy / Warning）
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# support 標籤的編碼（與 export_artifacts.py 一致）
HEALTHY, WARNING = 0, 1
STATUS_NAME = {HEALTHY: "Healthy", WARNING: "Warning"}


@dataclass(frozen=True)
class Verdict:
    """單筆讀數的判讀結果。"""

    status: str
    latent: np.ndarray            # (2,) 潛空間座標
    nearest_distance: float       # 到最近 support 點的距離
    reconstruction_error: float   # MSE(x, decode(mu))
    neighbour_rul: int            # 最近 support 點的真實 RUL（僅供解釋，非預測值）


class VaeDetector:
    """載入一次、重複使用。Streamlit 端用 @st.cache_resource 包起來。"""

    def __init__(self, assets: Path = ASSETS):
        w = np.load(assets / "vae_weights.npz")
        self._W1, self._b1 = w["fc1.weight"], w["fc1.bias"]
        self._Wmu, self._bmu = w["fc_mu.weight"], w["fc_mu.bias"]
        self._W2, self._b2 = w["fc2.weight"], w["fc2.bias"]
        self._W3, self._b3 = w["fc3.weight"], w["fc3.bias"]

        s = np.load(assets / "scaler.npz")
        self._scale, self._min = s["scale"], s["min"]
        self.data_min, self.data_max = s["data_min"], s["data_max"]

        sup = np.load(assets / "support.npz")
        self.support_z = sup["z"]
        self.support_labels = sup["labels"]
        self.support_rul = sup["rul"]

    # ---------- 前處理 ----------

    def scale(self, raw: np.ndarray) -> np.ndarray:
        """重現 sklearn MinMaxScaler.transform：X * scale_ + min_（不裁切，與訓練時一致）。"""
        return np.asarray(raw, dtype=np.float64) * self._scale + self._min

    # ---------- 網路 ----------

    def encode(self, x_scaled: np.ndarray) -> np.ndarray:
        """回傳 mu。輸入 (n, 21) 或 (21,)，輸出 (n, 2) 或 (2,)。"""
        x = np.atleast_2d(np.asarray(x_scaled, dtype=np.float32))
        h = np.maximum(x @ self._W1.T + self._b1, 0.0)
        mu = h @ self._Wmu.T + self._bmu
        return mu[0] if np.ndim(x_scaled) == 1 else mu

    def decode(self, z: np.ndarray) -> np.ndarray:
        zz = np.atleast_2d(np.asarray(z, dtype=np.float32))
        h = np.maximum(zz @ self._W2.T + self._b2, 0.0)
        out = h @ self._W3.T + self._b3
        return out[0] if np.ndim(z) == 1 else out

    # ---------- 判讀 ----------

    def nearest(self, z: np.ndarray, chunk: int = 4096):
        """1-NN：回傳 (最近點索引, 距離)。分塊計算，避免一次配置大矩陣。"""
        zz = np.atleast_2d(np.asarray(z, dtype=np.float32))
        idx = np.empty(len(zz), dtype=np.int64)
        dist = np.empty(len(zz), dtype=np.float32)
        for i in range(0, len(zz), chunk):
            block = zz[i:i + chunk]
            d = np.sqrt(((block[:, None, :] - self.support_z[None, :, :]) ** 2).sum(-1))
            j = d.argmin(axis=1)
            idx[i:i + chunk] = j
            dist[i:i + chunk] = d[np.arange(len(block)), j]
        return idx, dist

    def classify(self, raw_sensors: np.ndarray) -> Verdict:
        """單筆 21 個原始感測值 → 完整判讀結果。"""
        x_scaled = self.scale(raw_sensors)
        mu = self.encode(x_scaled)
        idx, dist = self.nearest(mu)
        recon = self.decode(mu)
        mse = float(np.mean((np.asarray(x_scaled, dtype=np.float32) - recon) ** 2))
        label = int(self.support_labels[idx[0]])
        return Verdict(
            status=STATUS_NAME[label],
            latent=np.asarray(mu, dtype=np.float64),
            nearest_distance=float(dist[0]),
            reconstruction_error=mse,
            neighbour_rul=int(self.support_rul[idx[0]]),
        )

    def classify_batch(self, raw_sensors: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(n, 21) → (狀態字串陣列, 潛空間座標, 最近距離)。"""
        mu = self.encode(self.scale(raw_sensors))
        idx, dist = self.nearest(mu)
        labels = self.support_labels[idx]
        status = np.where(labels == WARNING, "Warning", "Healthy")
        return status, mu, dist
