# Predictive Maintenance → Lean Operations 自動化改善案

> **從一個 AI 預測維護模型，到現場每天在用、能省人工、能算 ROI 的精實自動化系統。**
>
> 本專案以 NASA CMAPSS 航太引擎資料的 VAE 預測維護模型為核心，延伸為一套 **DMAIC 精實營運改善案**，結合 VBA、Power Automate (RPA)、Power BI 與 Power Apps 設計，展示資料分析師如何消除流程浪費並驗證效益。

## 🖥 線上互動展示

**https://landy-predictive-maintenance.streamlit.app/**

不用安裝任何東西，直接在瀏覽器裡拉動感測器看模型即時判讀、瀏覽 13,096 筆逐筆結果、檢視被漏判的機台，並調整 ROI 假設看效益如何重算。原始碼在 [`07-demo-app/`](07-demo-app/)。

---

## 🎯 這個專案在解決什麼

製造/半導體現場常見兩層浪費：

| 層 | 浪費 | 本專案的解法 |
|----|------|-------------|
| **第二層｜流程浪費**（本案主角） | 工程師每天手動下載 SAP、Excel 彙整、人工判讀、手動寄報表 | **VBA + Power Automate (RPA) + Power BI** 自動化，把數小時人工降到接近 0 |
| **第一層｜實體浪費**（技術亮點） | 設備非計畫停機、過度保養、待機 | **VAE 預測維護模型**自動判讀引擎健康、早期異常偵測 |

> 主從關係：**流程自動化是主角，AI 模型是它自動化處理的「判讀引擎」。** 兩層效益在 ROI 表分列，互相加分。

---

## 🔄 資料流（一條龍）

```
NASA CMAPSS 真實感測資料
        ↓
[01] VAE 模型逐筆判讀健康狀態  ──→  Accuracy 85.0%、Warning Recall 93.9%（實測）
        ↓
   model_predictions.csv          「系統每日輸出」：13,096 筆 Healthy/Warning
        ↓  包裝成髒的每日 SAP 匯出檔
[02] VBA 巨集：清理 → 去重 → 依機台彙總警告數
        ↓
[03] Power Automate 自動寄報表    [05] Power BI 儀表板    [04] Power Apps 現場查詢
        ↓
[06] ROI 效益驗證（實測🟢 / 假設🟡 分列）
```

> 模型的**判讀結果**是自動化流程的輸入。真實剩餘壽命（答案）只用來驗證模型準不準，
> 不會出現在匯出檔裡——因為現實中故障還沒發生，系統不可能知道答案。

---

## 🗂 專案結構（分階段）

| 資料夾 | 內容 | 對應 JD 關鍵字 |
|--------|------|---------------|
| [`01-core-model/`](01-core-model/) | VAE 模型判讀 + 評分腳本 + 驗證報告 | Data mining, predictive model |
| [`02-automation-vba/`](02-automation-vba/) | VBA 巨集：清理模擬 SAP 匯出 → 自動彙整報表 | VBA, replace manual Excel |
| [`03-rpa-power-automate/`](03-rpa-power-automate/) | Power Automate Desktop：RPA 自動下載+寄報表 | PowerAutomate, replace manual SAP download/email |
| [`04-powerapps-design/`](04-powerapps-design/) | 現場查詢 App 線框圖 + 畫面規格 | PowerAPPS, solutions developer |
| [`05-powerbi-dashboard/`](05-powerbi-dashboard/) | Power BI 儀表板：KPI、健康趨勢、HK 分層看板 | PowerBI, HK BI, dashboard |
| [`06-lean-lss/`](06-lean-lss/) | DMAIC、價值流圖、ROI 效益驗證 | Lean/LSS, benefit validator, ROI |
| [`07-demo-app/`](07-demo-app/) | 互動展示網站：即時判讀、自動化、RAG 問答、效益試算 | Python, RAG, prompt engineering |
| [`docs/`](docs/) | STAR 面試小抄、設計規格 | — |

---

## 📐 方法論：DMAIC

- **Define**：定義流程浪費（手動 SAP/Excel/Email 作業）與改善目標。
- **Measure**：量測基線人工工時（碼錶實測）。
- **Analyze**：價值流圖標出非加值步驟。
- **Improve**：VBA / RPA / Power BI / Power Apps 自動化。
- **Control**：Power BI HK 分層看板持續監控、異常自動通知。

---

## 📊 效益計算原則（誠信）

- 🟢 **實測值**：自動化單次耗時、模型 Precision/Recall/F1、消除的手動步驟數、開發工時。
- 🟡 **假設值（透明標註）**：每日執行次數、使用人數、年工作天、人力成本/小時。

ROI 模型（[`06-lean-lss/roi-validation.xlsx`](06-lean-lss/)）把假設做成明確輸入格，ROI 是其函數。**未捏造任何數字；公開資料集無真實成本者一律標為情境假設。**

---

## 🛠 技術棧

`Python` · `PyTorch (VAE)` · `MCP` · `VBA` · `Power Automate Desktop` · `Power BI` · `Power Apps (design)` · `Lean / Six Sigma (DMAIC)`

---

## 📌 進度

- [x] P0 基礎建置（repo、核心模型、README）
- [x] 01 核心模型評分（VAE 逐筆判讀，Accuracy 85% / Recall 93.9%）
- [x] P1 Lean 骨架（DMAIC、VSM）
- [x] P2 VBA 巨集（15 分鐘 → 約 1.6–1.8 秒，約 500×）
- [x] P3 RPA（Power Automate Desktop，端到端已驗證）
- [x] P4 Power Apps 設計稿（3 畫面線框圖）
- [x] P5 Power BI 儀表板（HK 三層看板）
- [x] P6 ROI 效益驗證（假設校準後：年省約 120 小時、首年 ROI 約 200%）
- [x] P7 收尾（面試小抄）
- [x] P8 互動展示網站（`07-demo-app/`：總覽、即時判讀＋導入新引擎、機隊軌跡、自動化、AI 助理、效益驗證）

## 🔑 關鍵成果（實測🟢 / 假設🟡）

| 指標 | 值 | 類型 |
|------|-----|------|
| 模型準確率 / 快故障召回 | 85.0% / 93.9% | 🟢 |
| 手動→自動處理時間（原始 13,750 列） | 15 分 → 1.6 秒／1.844 秒（約 500×；兩次實測 562×、488×） | 🟢 |
| 消除的靜默資料錯誤 | 去重 654 + 大小寫 2,001 筆 | 🟢 |
| 年省工時 / 首年 ROI | ~120 小時 / ~200% | 🟡 假設可替換 |
