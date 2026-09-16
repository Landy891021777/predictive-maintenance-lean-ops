"""
離線匯出：把訓練好的 VAE 與 NASA 原始資料，壓成 Streamlit app 執行時需要的最小資產。

=== 為什麼要有這一步 ===
線上環境（Streamlit Community Cloud 免費層，約 1GB RAM）不適合裝 PyTorch：
預設的 torch wheel 會拉 CUDA 相依（2GB+），部署很容易失敗或 OOM。

但這個 VAE 的 encoder 本質上只是
    h  = ReLU(x @ W1.T + b1)
    mu = h @ Wmu.T + bmu
三個矩陣運算。所以這支腳本在本機（有 torch）把權重匯出成 .npz，
線上就只用 NumPy 重算，完全不需要 PyTorch。

本腳本同時驗證「NumPy 版與 PyTorch 版輸出一致」，不一致就直接失敗，
避免線上偷偷跑出跟驗證報告不同的結果。

=== 輸出（07-demo-app/assets/）===
  vae_weights.npz    VAE 全部權重（encoder + decoder）
  scaler.npz         MinMaxScaler 的 scale_ / min_（完全重現 sklearn 的 transform）
  support.npz        support set 的 14,441 個 embedding 與標籤（1-NN 用）
  test_readings.npz  test_FD001 的 13,096 筆讀數（21 感測器，float32 壓縮）
  meta.json          門檻、欄位、感測器統計、驗證指標

執行：py -3 07-demo-app/build/export_artifacts.py
相依：requirements-dev.txt（torch / scikit-learn / pandas）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

# 與 01-core-model/scoring/score_engines.py 完全相同的設定
np.random.seed(34)
torch.manual_seed(34)

NASA_DIR = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
MODEL_PATH = NASA_DIR / "vae_model.pth"
ASSETS = Path(__file__).resolve().parent.parent / "assets"

INDEX_NAMES = ["unit_number", "time_cycles"]
SETTING_NAMES = [f"setting_{i}" for i in range(1, 4)]
SENSOR_NAMES = [f"s_{i}" for i in range(1, 22)]
COL_NAMES = INDEX_NAMES + SETTING_NAMES + SENSOR_NAMES

KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]
SUPPORT_QUANTILE = 0.33
INPUT_DIM, LATENT_DIM = 21, 2


class VAE(nn.Module):
    """必須與 vae_model.pth 的架構一致。"""

    def __init__(self, input_dim: int, latent_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc_mu = nn.Linear(64, latent_dim)
        self.fc_logvar = nn.Linear(64, latent_dim)
        self.fc2 = nn.Linear(latent_dim, 64)
        self.fc3 = nn.Linear(64, input_dim)
        self.relu = nn.ReLU()

    def encode(self, x):
        h = self.relu(self.fc1(x))
        return self.fc_mu(h), self.fc_logvar(h)


def add_rul(df: pd.DataFrame) -> pd.DataFrame:
    mx = df.groupby("unit_number")["time_cycles"].max()
    out = df.merge(mx.to_frame("max_cycle"), left_on="unit_number", right_index=True)
    out["RUL"] = out["max_cycle"] - out["time_cycles"]
    return out.drop(columns="max_cycle")


def numpy_encode(w: dict, x: np.ndarray) -> np.ndarray:
    """線上會用的那條路徑，在這裡先跑一次以便和 PyTorch 比對。"""
    h = np.maximum(x @ w["fc1.weight"].T + w["fc1.bias"], 0.0)
    return h @ w["fc_mu.weight"].T + w["fc_mu.bias"]


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 資料與前處理（重現 score_engines.py）----------
    train = add_rul(pd.read_csv(NASA_DIR / "train_FD001.txt", sep=r"\s+",
                                header=None, index_col=False, names=COL_NAMES))
    test = pd.read_csv(NASA_DIR / "test_FD001.txt", sep=r"\s+",
                       header=None, index_col=False, names=COL_NAMES)

    y = train["RUL"]
    X = train.drop(columns=INDEX_NAMES + SETTING_NAMES + ["RUL"])
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.3, random_state=42)

    scaler = MinMaxScaler()
    X_train_s = scaler.fit_transform(X_train)

    # ---------- 2. 權重匯出 ----------
    state = torch.load(MODEL_PATH, map_location="cpu")
    weights = {k: v.numpy().astype(np.float32) for k, v in state.items()}
    np.savez_compressed(ASSETS / "vae_weights.npz", **weights)

    # ---------- 3. NumPy vs PyTorch 一致性驗證 ----------
    vae = VAE(INPUT_DIM, LATENT_DIM)
    vae.load_state_dict(state)
    vae.eval()
    with torch.no_grad():
        mu_torch, _ = vae.encode(torch.tensor(X_train_s, dtype=torch.float32))
    z_torch = mu_torch.numpy()
    z_numpy = numpy_encode(weights, X_train_s.astype(np.float32))

    max_diff = float(np.abs(z_torch - z_numpy).max())
    print(f"[驗證] NumPy vs PyTorch encoder 最大絕對誤差 = {max_diff:.3e}")
    if max_diff > 1e-5:
        raise SystemExit(f"NumPy 版與 PyTorch 版輸出不一致（{max_diff:.3e}），中止匯出。")

    # ---------- 4. scaler 參數 ----------
    # sklearn 的 transform 就是 X * scale_ + min_，直接存這兩個陣列即可完全重現
    np.savez_compressed(
        ASSETS / "scaler.npz",
        scale=scaler.scale_.astype(np.float64),
        min=scaler.min_.astype(np.float64),
        data_min=scaler.data_min_.astype(np.float64),
        data_max=scaler.data_max_.astype(np.float64),
    )

    # ---------- 5. support set ----------
    y_train_a = np.asarray(y_train)
    support_cut = float(np.quantile(y_train_a, SUPPORT_QUANTILE))
    # 0 = Low(Healthy)，1 = High(Warning)
    support_labels = (y_train_a <= support_cut).astype(np.int8)
    np.savez_compressed(
        ASSETS / "support.npz",
        z=z_numpy.astype(np.float32),
        labels=support_labels,
        rul=y_train_a.astype(np.int32),
    )

    # ---------- 6. test 讀數（即時判讀頁要載入真實引擎的某個 cycle）----------
    # 必須存 float64。部分感測器數值本身很大但全距極窄（例如 s_13 約 2388、全距僅 0.49），
    # 存成 float32 後，MinMaxScaler 把它映射到 [0,1] 時會把 float32 的捨入誤差放大約
    # 1000 倍（2.4e-4 量級），足以讓 1-NN 在邊界上改判。實測會造成 13,096 筆中 61 筆
    # 與 model_predictions.csv 不一致。
    np.savez_compressed(
        ASSETS / "test_readings.npz",
        unit=test["unit_number"].values.astype(np.int16),
        cycle=test["time_cycles"].values.astype(np.int16),
        sensors=test[SENSOR_NAMES].values.astype(np.float64),
    )

    # ---------- 7. meta：門檻、感測器統計、驗證指標 ----------
    raw_train_sensors = X.values
    const_mask = raw_train_sensors.std(axis=0) < 1e-9
    meta = {
        "sensor_names": SENSOR_NAMES,
        "key_sensors": [f"s_{s}" for s in KEY_SENSORS],
        "constant_sensors": [SENSOR_NAMES[i] for i in np.where(const_mask)[0]],
        "support_quantile": SUPPORT_QUANTILE,
        "support_cut_rul": support_cut,
        "support_size": int(len(z_numpy)),
        "latent_dim": LATENT_DIM,
        "input_dim": INPUT_DIM,
        "sensor_stats": {
            name: {
                "min": float(raw_train_sensors[:, i].min()),
                "max": float(raw_train_sensors[:, i].max()),
                "mean": float(raw_train_sensors[:, i].mean()),
                "p01": float(np.percentile(raw_train_sensors[:, i], 1)),
                "p50": float(np.percentile(raw_train_sensors[:, i], 50)),
                "p99": float(np.percentile(raw_train_sensors[:, i], 99)),
                "constant": bool(const_mask[i]),
            }
            for i, name in enumerate(SENSOR_NAMES)
        },
        "numpy_vs_torch_max_abs_diff": max_diff,
        "source": {
            "weights": str(MODEL_PATH),
            "dataset": "NASA CMAPSS FD001",
            "scoring_script": "01-core-model/scoring/score_engines.py",
        },
    }
    (ASSETS / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---------- 8. 摘要 ----------
    print(f"[匯出] support set        {len(z_numpy):,} 點，RUL 分界 = {support_cut:.1f}")
    print(f"[匯出] test 讀數          {len(test):,} 筆 × {len(SENSOR_NAMES)} 感測器")
    print(f"[匯出] 常數感測器（無變異）{meta['constant_sensors']}")
    print("\n檔案大小：")
    for f in sorted(ASSETS.glob("*")):
        print(f"  {f.name:22s} {f.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
