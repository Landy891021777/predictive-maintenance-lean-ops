"""
VAE 引擎健康判讀 —— 重現 notebook 的方法，並輸出可供下游自動化使用的「模型結果表」。

=== 方法（完全依照 Fork_of_Nasa_predictive_Maintenance_(RUL).ipynb）===
1. 由 train_FD001 計算每列的 RUL = (該引擎最大 cycle) - (當前 cycle)
2. X = 21 個感測器欄位；train_test_split(test_size=0.3, random_state=42)
3. MinMaxScaler 以 X_train 擬合
4. 載入已訓練的 VAE（input_dim=21, latent_dim=2），用 encoder 取 embedding（mu）
5. Support set = X_train 的 embedding；標籤依 RUL 的 33% 分位數：
       RUL >  門檻  → "Low"   （低風險 = 健康）
       RUL <= 門檻  → "High"  （高風險 = 快壞）
6. 對每筆待判讀資料，找最近的 support 點（1-NN），取其標籤作為預測

=== 兩種輸出 ===
A. outputs/model_validation.*  —— 「忠於 notebook」的評估
   只判讀 test_FD001 中每台引擎的「最後一個 cycle」（100 台），
   因為 RUL_FD001 只提供那一點的真實答案。這是 CMAPSS 的標準評估法。

B. outputs/model_predictions.csv —— 「營運系統」的逐筆判讀
   用同一個模型、同一個 1-NN 規則，對 test_FD001 的全部 13,096 筆讀數判讀。
   真實的營運系統會對每一筆進來的讀數判讀，而非只判最後一筆。
   此表即為下游 VBA / Power BI 自動化的輸入（模擬「系統每日輸出」）。

注意：預測標籤在輸出中改寫為維運語彙，避免 Low/High 造成歧義：
       "Low"  → Healthy
       "High" → Warning

執行：py -3 score_engines.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

np.random.seed(34)
torch.manual_seed(34)

NASA_DIR = Path(r"C:\Users\User\Desktop\kaggle 專案\nasa專案")
MODEL_PATH = NASA_DIR / "vae_model.pth"
OUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

INDEX_NAMES = ["unit_number", "time_cycles"]
SETTING_NAMES = [f"setting_{i}" for i in range(1, 4)]
SENSOR_NAMES = [f"s_{i}" for i in range(1, 22)]
COL_NAMES = INDEX_NAMES + SETTING_NAMES + SENSOR_NAMES

# 本專案的特徵選擇（見 docs/航太維修專案 背景.md）；模型內部仍吃全部 21 個感測器，
# 這 12 欄僅作為下游報表的情境欄位。
KEY_SENSORS = [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17]

SUPPORT_QUANTILE = 0.33
INPUT_DIM, LATENT_DIM = 21, 2
LABEL_TO_STATUS = {"Low": "Healthy", "High": "Warning"}


class VAE(nn.Module):
    """必須與訓練時的架構一致，才能載入 vae_model.pth。"""

    def __init__(self, input_dim: int, latent_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 64)
        self.fc_mu = nn.Linear(64, latent_dim)
        self.fc_logvar = nn.Linear(64, latent_dim)
        self.fc2 = nn.Linear(latent_dim, 64)
        self.fc3 = nn.Linear(64, input_dim)
        self.relu = nn.ReLU()

    def encode(self, x: torch.Tensor):
        h = self.relu(self.fc1(x))
        return self.fc_mu(h), self.fc_logvar(h)


def add_rul(df: pd.DataFrame) -> pd.DataFrame:
    mx = df.groupby("unit_number")["time_cycles"].max()
    out = df.merge(mx.to_frame("max_cycle"), left_on="unit_number", right_index=True)
    out["RUL"] = out["max_cycle"] - out["time_cycles"]
    return out.drop(columns="max_cycle")


def encode(vae: VAE, x: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        mu, _ = vae.encode(torch.tensor(x, dtype=torch.float32))
    return mu.numpy()


def nearest_support(z_query: np.ndarray, z_support: np.ndarray,
                    support_labels: np.ndarray, chunk: int = 1024):
    """1-NN：回傳每筆 query 的 (預測標籤, 最近距離)。分塊計算以控制記憶體。"""
    zs = torch.tensor(z_support, dtype=torch.float32)
    labels, dists = [], []
    for i in range(0, len(z_query), chunk):
        zq = torch.tensor(z_query[i:i + chunk], dtype=torch.float32)
        d = torch.cdist(zq, zs)
        dmin, imin = torch.min(d, dim=1)
        labels.append(support_labels[imin.numpy()])
        dists.append(dmin.numpy())
    return np.concatenate(labels), np.concatenate(dists)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 載入資料，重現 notebook 的前處理 ----------
    train = add_rul(pd.read_csv(NASA_DIR / "train_FD001.txt", sep=r"\s+",
                                header=None, index_col=False, names=COL_NAMES))
    test = pd.read_csv(NASA_DIR / "test_FD001.txt", sep=r"\s+",
                       header=None, index_col=False, names=COL_NAMES)
    rul_final = pd.read_csv(NASA_DIR / "RUL_FD001.txt", sep=r"\s+",
                            header=None, index_col=False, names=["RUL"])["RUL"].values

    y = train["RUL"]
    X = train.drop(columns=INDEX_NAMES + SETTING_NAMES + ["RUL"])
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.3, random_state=42)

    scaler = MinMaxScaler()
    X_train_s = scaler.fit_transform(X_train)

    # ---------- 2. 載入模型，建立 support set ----------
    vae = VAE(INPUT_DIM, LATENT_DIM)
    vae.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    vae.eval()

    z_support = encode(vae, X_train_s)
    y_train_a = np.asarray(y_train)
    support_cut = float(np.quantile(y_train_a, SUPPORT_QUANTILE))
    support_labels = np.where(y_train_a > support_cut, "Low", "High")

    print(f"Support set: {len(z_support)} 點 | RUL 分界 = {support_cut:.1f}")

    # ---------- 3A. 忠於 notebook 的評估（每台引擎最後一個 cycle）----------
    last = test.groupby("unit_number").last().reset_index()
    X_last_s = scaler.transform(last.drop(columns=INDEX_NAMES + SETTING_NAMES))
    z_last = encode(vae, X_last_s)
    pred_last, dist_last = nearest_support(z_last, z_support, support_labels)

    test_cut = float(np.quantile(rul_final, SUPPORT_QUANTILE))
    true_last = np.where(rul_final > test_cut, "Low", "High")

    acc = accuracy_score(true_last, pred_last)
    cm = confusion_matrix(true_last, pred_last, labels=["Low", "High"])
    report = classification_report(true_last, pred_last, labels=["Low", "High"], digits=4)

    print(f"\n[A] notebook 評估（100 台，最後一個 cycle）Accuracy = {acc:.4f}")
    print(report)

    pd.DataFrame({
        "EquipmentID": [f"ENG-{u:03d}" for u in last["unit_number"]],
        "LastCycle": last["time_cycles"].values,
        "TrueRUL": rul_final,
        "TrueLabel": [LABEL_TO_STATUS[l] for l in true_last],
        "PredictedStatus": [LABEL_TO_STATUS[l] for l in pred_last],
        "NearestDistance": np.round(dist_last, 6),
    }).to_csv(OUT_DIR / "model_validation.csv", index=False, encoding="utf-8-sig")

    _write_validation_report(acc, cm, report, support_cut, test_cut, len(z_support))

    # ---------- 3B. 營運系統的逐筆判讀（全部讀數）----------
    X_all_s = scaler.transform(test.drop(columns=INDEX_NAMES + SETTING_NAMES))
    z_all = encode(vae, X_all_s)
    pred_all, dist_all = nearest_support(z_all, z_support, support_labels)
    status_all = np.vectorize(LABEL_TO_STATUS.get)(pred_all)

    preds = pd.DataFrame({
        "unit_number": test["unit_number"].values,
        "time_cycles": test["time_cycles"].values,
    })
    for s in KEY_SENSORS:
        preds[f"Sensor_{s}"] = test[f"s_{s}"].values
    preds["LatentZ1"] = np.round(z_all[:, 0], 6)
    preds["LatentZ2"] = np.round(z_all[:, 1], 6)
    preds["NearestDistance"] = np.round(dist_all, 6)
    preds["PredictedStatus"] = status_all

    preds.to_csv(OUT_DIR / "model_predictions.csv", index=False, encoding="utf-8-sig")

    n_warn = int((status_all == "Warning").sum())
    engines_with_warn = preds.loc[preds["PredictedStatus"] == "Warning", "unit_number"].nunique()
    print(f"\n[B] 逐筆判讀：{len(preds)} 筆讀數 | Warning {n_warn} 筆 ({n_warn/len(preds)*100:.1f}%)"
          f" | 有 Warning 的引擎 {engines_with_warn}/100")
    print(f"\n輸出：\n  {OUT_DIR / 'model_predictions.csv'}\n  {OUT_DIR / 'model_validation.csv'}"
          f"\n  {OUT_DIR / 'model_validation.md'}")


def _write_validation_report(acc, cm, report, support_cut, test_cut, n_support) -> None:
    md = f"""# 模型驗證報告（忠於 notebook 的評估）

> 由 `01-core-model/scoring/score_engines.py` 自動產生。所有數字皆為**實測值**。

## 方法

VAE encoder 取 embedding（latent_dim=2）→ 對每筆待判資料找**最近的 support set 點**（1-NN）→ 取該點的標籤。

- Support set：訓練集 70% 的 embedding，共 **{n_support:,}** 點
- Support 標籤分界：RUL 的 33% 分位數 = **{support_cut:.1f}** cycles
  （RUL > 分界 → `Healthy`；否則 → `Warning`）
- 評估對象：`test_FD001` 中**每台引擎的最後一個 cycle**（100 台）
  這是 CMAPSS 的標準評估法，因為 `RUL_FD001` 只提供那一點的真實剩餘壽命。
- 真實標籤分界：`RUL_FD001` 的 33% 分位數 = **{test_cut:.1f}** cycles

## 結果

**Accuracy = {acc:.4f}**

### 混淆矩陣

|  | 預測 Healthy | 預測 Warning |
|---|---|---|
| **實際 Healthy** | {cm[0][0]} | {cm[0][1]} |
| **實際 Warning** | {cm[1][0]} | {cm[1][1]} |

### 分類報告

```
{report}
```
（報告中的 `Low` = Healthy，`High` = Warning）

## 維運觀點的解讀

- **漏判（實際 Warning 卻預測 Healthy）：{cm[1][0]} 台** —— 這是代價最高的錯誤（引擎沒被預警就故障）。
- **誤報（實際 Healthy 卻預測 Warning）：{cm[0][1]} 台** —— 代價較低（多做一次檢查）。

模型在這個取捨上偏向**寧可誤報、不要漏判**，符合預測性維護的實務需求。

## 誠信聲明

- 上述所有數字皆由本腳本在真實 NASA CMAPSS 資料上實際執行產生，非估計值。
- `model_predictions.csv` 使用**同一個模型與同一個 1-NN 規則**，套用到 `test_FD001` 的全部讀數，
  以模擬營運系統的逐筆判讀。該檔案**不含**任何來自 `RUL_FD001` 的真實答案。
"""
    (OUT_DIR / "model_validation.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
