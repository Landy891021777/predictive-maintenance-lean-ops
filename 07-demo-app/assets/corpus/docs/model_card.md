# VAE 異常偵測模型卡

> 🟢 真實專案文件

## 1. 模型概要

模型：變分自編碼器（VAE），架構 21 → 64 → 2（潛空間）→ 64 → 21，以 PyTorch 訓練。
資料：NASA CMAPSS FD001，訓練集 100 台引擎、20,631 筆讀數，21 個感測器。
用途：將每筆感測讀數判讀為 Healthy 或 Warning，作為自動化報表流程的判讀引擎。
方法：模型本身不是分類器，而是學習把高維感測訊號壓縮成有結構的 2 維表徵，
再以最近鄰（1-NN）在表徵空間中比對 14,441 筆歷史讀數完成分類。
這種作法適合故障樣本稀少、標註不足的情境（few-shot）。

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*

## 2. 判讀規則與參數

- 前處理：MinMaxScaler，以訓練集 70% 擬合（train_test_split, test_size=0.3, random_state=42）
- Support set：訓練集 70% 的 embedding，共 14,441 點
- Support 標籤分界：訓練集剩餘壽命的 33% 分位數 = 67.0 cycles
  （剩餘壽命 > 分界為 Healthy，≤ 分界為 Warning）
- 判讀：取潛空間中最近的 support 點標籤

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*

## 3. 評估方法

評估對象：test_FD001 中每台引擎的最後一個 cycle，共 100 台。
這是 CMAPSS 的標準評估法，因為 RUL_FD001 只提供最後那一點的真實剩餘壽命。
真實標籤分界：RUL_FD001 的 33% 分位數 = 52.7 cycles。
兩個分界各自在自己的分佈上計算，互不洩漏。
逐筆判讀的 13,096 筆讀數（model_predictions.csv）不含真實答案，是模擬營運系統的輸出。

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*

## 4. 評估結果

Accuracy = 0.8500
混淆矩陣（列為實際、欄為預測）：
- 實際 Healthy：預測 Healthy 54 台、預測 Warning 13 台（誤報）
- 實際 Warning：預測 Healthy 2 台（漏判）、預測 Warning 31 台
Warning 類：precision 0.7045、recall 0.9394
Healthy 類：precision 0.9643、recall 0.8060
模型偏向寧可誤報、不要漏判：誤報一次的代價是多做一次檢查，漏判一次的代價是引擎沒被預警就故障。

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*

## 5. 已知錯誤：漏判與誤報

漏判 2 台（最後一筆讀數被判為 Healthy）：
- ENG-064：最後 cycle 168，真實剩餘壽命 28 cycles。真正的漏判：離分界線 24.7 個 cycle，讀數在潛空間中仍落在健康樣本附近。
- ENG-072：最後 cycle 131，真實剩餘壽命 50 cycles。標籤邊界效應：只比分界線內側少 2.7 個 cycle，分位數稍微移動就不算錯。
誤報 13 台：ENG-003、ENG-007、ENG-021、ENG-030、ENG-043、ENG-057、ENG-060、ENG-062、ENG-063、ENG-084、ENG-093、ENG-094、ENG-098。

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*

## 6. 補充觀察：看連續讀數而非單筆讀數

若不看最後一筆讀數，而是套用《異常處置 SOP》的趨勢分級（最近 10 筆中 Warning 筆數），
在同一份測試資料上觀察到：
- 真實標籤為 Warning 的 33 台引擎，有 33 台曾觸發 L2（≥3 筆），包含上述兩台漏判引擎
- 觸發 L3（≥7 筆）的 33 台中，30 台真實標籤為 Warning、3 台為 Healthy
限制：分級門檻雖為事先訂定，但此觀察與模型評估使用同一份測試資料，且比較的是「整個觀測期」
與「最後一筆」兩種不同的評估方式，屬事後觀察，未經獨立資料驗證，不應視為模型效能指標。

*來源：由 model_predictions.csv 依 SOP 門檻計算，並對照 model_validation.csv 的真實標籤*

## 7. 限制與部署

限制：
- 僅在 FD001（單一運轉條件、單一失效模式）上訓練與評估，未驗證於多工況資料
- 公開模擬資料集，無真實維修成本資料；成本效益（維護成本 −84%、停機 −36%）為情境推估
- 二分類是刻意的設計取捨：現場需要的是「要不要處理」的決策，而非精確的剩餘壽命數字
部署：
- 網站上的即時判讀以純 NumPy 重算 VAE，權重自 PyTorch 匯出
- NumPy 版與 PyTorch 版最大絕對誤差 7.2e-07，
  並驗證可逐格重現上述評估結果與 13,096 筆逐筆判讀

*來源：01-core-model/outputs/model_validation.csv、07-demo-app/assets/meta.json（實測）*
