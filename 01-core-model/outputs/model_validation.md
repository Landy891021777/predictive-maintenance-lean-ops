# 模型驗證報告（忠於 notebook 的評估）

> 由 `01-core-model/scoring/score_engines.py` 自動產生。所有數字皆為**實測值**。

## 方法

VAE encoder 取 embedding（latent_dim=2）→ 對每筆待判資料找**最近的 support set 點**（1-NN）→ 取該點的標籤。

- Support set：訓練集 70% 的 embedding，共 **14,441** 點
- Support 標籤分界：RUL 的 33% 分位數 = **67.0** cycles
  （RUL > 分界 → `Healthy`；否則 → `Warning`）
- 評估對象：`test_FD001` 中**每台引擎的最後一個 cycle**（100 台）
  這是 CMAPSS 的標準評估法，因為 `RUL_FD001` 只提供那一點的真實剩餘壽命。
- 真實標籤分界：`RUL_FD001` 的 33% 分位數 = **52.7** cycles

## 結果

**Accuracy = 0.8500**

### 混淆矩陣

|  | 預測 Healthy | 預測 Warning |
|---|---|---|
| **實際 Healthy** | 54 | 13 |
| **實際 Warning** | 2 | 31 |

### 分類報告

```
              precision    recall  f1-score   support

         Low     0.9643    0.8060    0.8780        67
        High     0.7045    0.9394    0.8052        33

    accuracy                         0.8500       100
   macro avg     0.8344    0.8727    0.8416       100
weighted avg     0.8786    0.8500    0.8540       100

```
（報告中的 `Low` = Healthy，`High` = Warning）

## 維運觀點的解讀

- **漏判（實際 Warning 卻預測 Healthy）：2 台** —— 這是代價最高的錯誤（引擎沒被預警就故障）。
- **誤報（實際 Healthy 卻預測 Warning）：13 台** —— 代價較低（多做一次檢查）。

模型在這個取捨上偏向**寧可誤報、不要漏判**，符合預測性維護的實務需求。

## 誠信聲明

- 上述所有數字皆由本腳本在真實 NASA CMAPSS 資料上實際執行產生，非估計值。
- `model_predictions.csv` 使用**同一個模型與同一個 1-NN 規則**，套用到 `test_FD001` 的全部讀數，
  以模擬營運系統的逐筆判讀。該檔案**不含**任何來自 `RUL_FD001` 的真實答案。
