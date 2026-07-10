# 01 — VAE 預測性維護核心模型

> 整條資料流的起點：模型對每一筆感測讀數判讀健康狀態，產出「系統每日輸出」。

---

## 方法

以 NASA CMAPSS FD001 航太引擎感測資料訓練 **VAE（變分自編碼器）**，用 encoder 把 21 維感測讀數壓縮成 2 維 embedding，再以 **Few-shot 最近鄰（1-NN）** 判讀健康狀態。

1. 由 `train_FD001` 計算每列的 RUL（剩餘壽命）= 該引擎最大 cycle − 當前 cycle
2. `train_test_split(test_size=0.3, random_state=42)`，`MinMaxScaler` 以 `X_train` 擬合
3. 載入已訓練的 VAE（`input_dim=21`, `latent_dim=2`），取 encoder 的 `mu` 作為 embedding
4. **Support set** = 訓練集的 embedding（14,441 點），依 RUL 的 33% 分位數（= 67 cycles）標記：
   - `RUL > 67` → `Healthy`
   - `RUL ≤ 67` → `Warning`
5. 對每筆待判讀資料，找**最近的 support 點**，取其標籤作為預測

---

## 驗證結果（🟢 實測）

依 CMAPSS 標準評估法：只判讀 `test_FD001` 中每台引擎的**最後一個 cycle**（100 台），
因為 `RUL_FD001` 只提供那一點的真實剩餘壽命。

| 指標 | 數值 |
|------|------|
| **Accuracy** | **85.0%** |
| Warning 的 Recall | **93.9%**（33 台快壞的，抓到 31 台） |
| Warning 的 Precision | 70.5% |
| **漏判**（該壞沒抓到） | **2 台** |
| 誤報 | 13 台 |

模型偏向**寧可誤報、不要漏判**——符合預測性維護的實務取捨（多檢查一次的成本，遠低於非計畫停機）。

完整報告：[`outputs/model_validation.md`](outputs/model_validation.md)

---

## 產出

| 檔案 | 內容 |
|------|------|
| [`outputs/model_predictions.csv`](outputs/) | **13,096 筆逐列判讀**（模擬營運系統的每日輸出）。含 embedding 座標、最近距離、`PredictedStatus`。**不含真實答案。** |
| [`outputs/model_validation.csv`](outputs/) | 100 台引擎的驗證明細（含真實 RUL，僅供驗證） |
| [`outputs/model_validation.md`](outputs/model_validation.md) | 驗證報告：混淆矩陣、分類報告 |

### 逐筆判讀的統計

- 13,096 筆讀數中，模型判 `Warning` **1,693 筆（12.9%）**
- **警告率 vs 真實剩餘壽命的相關係數 = −0.664**
  - 警告率最高的 10 台：平均真實剩餘壽命 **25.0** cycles
  - 警告率最低的 10 台：平均真實剩餘壽命 **102.7** cycles

> 這證明「每台機台的警告率」是一個**真的能分辨機台好壞**的 KPI，可以放上儀表板做預警。

---

## 執行

```bash
py -3 scoring/score_engines.py
```

需要（不會修改這些原始檔）：
- `C:\Users\User\Desktop\kaggle 專案\nasa專案\train_FD001.txt`
- `…\test_FD001.txt`、`…\RUL_FD001.txt`、`…\vae_model.pth`

---

## 誠信說明

- `score_engines.py` **完全依照** [`notebooks/Fork_of_Nasa_predictive_Maintenance_(RUL).ipynb`](notebooks/) 的方法重現，未更動模型或判讀規則。
- 上表所有數字皆由腳本在真實資料上實際執行產生，非估計值。
- notebook 依 CMAPSS 慣例只評估「最後一個 cycle」；`model_predictions.csv` 將**同一個模型、同一個 1-NN 規則**套用到全部讀數，以模擬營運系統的逐筆判讀。85% 準確率僅適用於前者，不會挪用到後者。

---

## 檔案結構

```
01-core-model/
├── notebooks/    原始訓練與評估 notebook
├── scoring/      score_engines.py — 重現方法並輸出結果表
├── outputs/      模型結果表與驗證報告
├── server/       vae_mcp_server.py（MCP 封裝，本次自動化流程未使用）
└── docs/         專案背景、流程圖、面試小抄
```
