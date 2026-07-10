# P2 — VBA 巨集：取代手動 SAP 資料清理與彙整

> **對應 ASML JD：** *"use macro to replace manual download from SAP, manual summary in excel"*
> **消除的浪費：** Motion（反覆匯入貼上）、Overprocessing（每天重做同樣清理）、Defects（人工修髒資料出錯）

---

## 這一步在整條資料流的位置

```
  [01-core-model] VAE 模型逐筆判讀每一筆感測讀數
            ↓
    model_predictions.csv          ← 「系統每日輸出」（Healthy / Warning）
            ↓  包裝成髒的 SAP 匯出檔
    SAP_EXPORT_2026070*.csv
            ↓  ★ 本階段：[VBA] 清理 → 去重 → 依機台彙總警告數
    CleanData + Summary
            ↓
    [P3 Power Automate] 自動寄報表    [P5 Power BI] 儀表板
```

**關鍵設計**：匯出檔裡只有**模型的判讀**（`PredictedStatus`），**沒有任何真實答案**。
真實剩餘壽命（`RUL_FD001`）只出現在 [`01-core-model/outputs/model_validation.csv`](../01-core-model/outputs/model_validation.csv)，僅用於驗證模型準確率。

> 理由很簡單：**現實中故障還沒發生，系統不可能知道引擎還剩幾個週期。** 把答案放進輸入，模型就變成裝飾品了。

---

## 資料來源與誠信聲明

| 欄位 | 真實 / 模擬 | 說明 |
|------|------------|------|
| `EquipmentID` | 🟢 **真實** | 100 台引擎的真實 unit 編號 |
| `Cycle` | 🟢 **真實** | 真實運轉週期 |
| `Sensor_2 … Sensor_17`（12 欄） | 🟢 **真實** | 真實感測器量測值 |
| `LatentZ1` / `LatentZ2` | 🟢 **真實** | VAE encoder 產生的 embedding 座標 |
| `NearestDistance` | 🟢 **真實** | 到最近 support set 點的距離 |
| `PredictedStatus` | 🟢 **真實** | **模型的判讀**（Healthy / Warning） |
| `ExportDate` | 🟡 模擬 | 每台引擎的 cycle 依時序切成 3 天批次匯出 |
| `Timestamp` | 🟡 模擬 | 由 Cycle 推導 |
| `WorkOrder` | 🟡 模擬 | CMAPSS 無此欄位（屬 SAP/ERP 側） |
| `MaintenanceCost` | 🟡 模擬 | CMAPSS 無此欄位（屬 SAP/ERP 側） |

### 兩種切法（資料夾）

同一份模型判讀結果，用兩種方式切成「每日匯出檔」，各講不同的故事：

| 資料夾 | 語意 | 切法 | 資料量 | Warning 趨勢 |
|--------|------|------|--------|-------------|
| **`sample-data/lifecycle/`**（主力，已實測計時） | 累積歷史讀數，分批下載 | 每台引擎生命週期依 cycle 平均切 3 段 | 13,096 列 | 156→286→**1,251**（明顯遞增） |
| **`sample-data/snapshot/`**（艦隊快照） | 每天全艦隊各回報當下一筆 | 每台只取最後 3 個 cycle（day1=N-2…day3=N） | 300 列 | 41%→38%→44%（大致持平） |

**為何 snapshot 的 Warning 持平？** 連續三個 cycle（三個時間單位）健康幾乎不變——這是真實的。snapshot 回答的是「**現在誰該修**」（今日艦隊狀態），而非「怎麼退化」。兩種版本都誠實，只是視角不同。

#### lifecycle 各檔明細
| 匯出檔 | 資料列（去重後） | 引擎數 | 模型判 Warning |
|--------|----------------|--------|---------------|
| `SAP_EXPORT_20260701.csv` | 4,401 | 100 | 156 |
| `SAP_EXPORT_20260702.csv` | 4,362 | 100 | 286 |
| `SAP_EXPORT_20260703.csv` | 4,333 | 100 | **1,251** |
| **合計** | **13,096**（原始 13,750） | 100 | **1,693** |

> 每個匯出檔都含全部 100 台引擎。lifecycle 的三個「匯出日」代表三個**時間區段**，非嚴格的連續三天；snapshot 的三天才是真正連續的三天。
>
> **巨集執行時會詢問要處理哪一份**（Yes=lifecycle / No=snapshot / Cancel=自選資料夾）。ROI 效益驗證（P6）使用 lifecycle 的實測計時。

### 刻意加入的髒資料

模擬真實 SAP 匯出的品質問題，**非模型或資料集本身的問題**：

| 髒資料類型 | 比例 | 單檔實際筆數 |
|-----------|------|-------------|
| `EquipmentID` 前後空白 | 15% | 696 |
| `EquipmentID` 小寫 | 10% | 444 |
| `PredictedStatus` 小寫 / 全大寫 | 15% | 431 / 250 |
| `ExportDate` 三種格式混用 | 100% | `2026/07/01`、`01-Jul-2026`、`2026-07-01` |
| `MaintenanceCost` 千分位逗號 | ~40% | 1,151 |
| `MaintenanceCost` 缺值 | 7% | 315 |
| `NearestDistance` 缺值 | 3% | 123 |
| 重複列 | 5% | 220 |

> **為何用分號 `;` 分隔？** SAP 匯出常用分號，且能讓千分位逗號 `1,234.56` 不破壞欄位。
>
> **為何 `.bas` 的註解是英文？** VBA 編輯器匯入 `.bas` 時以系統 ANSI 編碼（繁中 Windows 為 Big5）讀取，若檔案含 UTF-8 中文會變亂碼並導致**編譯錯誤**。因此程式碼保持純 ASCII，中文詳解一律放在本 README。這同時符合 JD 的 business English 要求。

---

## 這個巨集做什麼

把「手動 7 步」變成「一鍵」：

| 手動流程 | 巨集自動做 |
|----------|-----------|
| 逐一開啟 3 個 CSV | 自動掃描 `sample-data/` 讀取全部 `.csv` |
| 去除機台代號前後空白、統一大小寫 | `Trim` + `UCase` |
| 統一 `Warning` / `warning` / `WARNING` | `NormalizeStatus()` |
| 統一 3 種混用的日期格式 | `NormalizeDate()` |
| 手動找出並刪除重複列 | 以「日期\|機台\|Cycle\|時戳\|工單」為鍵去重 |
| 千分位數字 `1,234.56` 轉數值 | `CleanNumber()` |
| 標記缺值 | 自動統計 |
| 樞紐分析做機台彙總 | 自動產生 `Summary`（讀數／警告數／警告率／平均距離／成本合計） |

**額外：** 巨集內建 `Timer`，執行完顯示**實測耗時（秒）**並寫入 `Summary!B9` — 這是 P6 ROI 表的 🟢 實測輸入值。

---

## 檔案

| 檔案 | 說明 |
|------|------|
| `sample-data/generate_sample_data.py` | 把模型結果包裝成髒的 SAP 匯出檔 |
| `sample-data/SAP_EXPORT_2026070*.csv` | 3 個模擬匯出檔，共 13,750 列 × 22 欄 |
| `src/CleanAndSummarize.bas` | VBA 巨集原始碼 |

### 重新產生資料
```bash
# 1. 先跑模型判讀（產出 model_predictions.csv）
py -3 ../01-core-model/scoring/score_engines.py
# 2. 再包裝成 SAP 匯出檔（兩種都產生）
py -3 sample-data/generate_sample_data.py          # both（預設）
py -3 sample-data/generate_sample_data.py lifecycle # 只產 lifecycle
py -3 sample-data/generate_sample_data.py snapshot  # 只產 snapshot
```
亂數種子固定為 42，結果可重現。

---

## 安裝與執行

1. 開啟 Excel → 新增空白活頁簿 → **另存為「Excel 啟用巨集的活頁簿 (.xlsm)」**，存到本資料夾 `02-automation-vba\` 底下。
2. `Alt + F11` → **檔案 → 匯入檔案** → 選 `src\CleanAndSummarize.bas`
   （若已有舊版模組，先右鍵 **移除**，匯出選「否」）
3. **偵錯 → 編譯 VBAProject**（沒跳視窗＝通過）
4. `Alt + Q` 回 Excel → `Alt + F8` → `CleanAndSummarize` → **執行**

**預期結果（這些數字應該完全對得上）：**
```
Files read              : 3
Raw rows read           : 13750
Duplicate rows removed  : 654
Clean rows              : 13096
Status case normalized  : 2001
Total WARNING readings  : 1693
Missing NearestDistance : 386
Missing MaintenanceCost : 901
ELAPSED: ?.??? seconds
```

---

## 效益量測：手動 vs 自動（待實測填入）

| 項目 | 手動流程 | VBA 自動流程 |
|------|---------|-------------|
| 步驟數 | 8 步 | 1 步（一鍵） |
| 單次耗時 | **15 分鐘（900 秒）** 🟢 | **1.6 秒** 🟢 |
| 單次省時 | — | **898.4 秒 ≈ 14.97 分（−99.8%）** |
| 速度 | — | **約 562× 快** |
| 處理列數 | 13,750 | 13,750 |
| 重複列處理 | 人工比對，易漏 | 自動去除 654 筆 |
| 狀態大小寫 | 人工檢查，易漏 | 自動正規化 2,001 筆 |
| **正確性** | **易出錯（見下）** | 規則固定，可重現 |

> 🟢 **實測值**：手動流程親自碼錶計時 15 分鐘；巨集執行 `Timer` 回報 1.6 秒。
> 年度效益（需乘上每日次數／人數／工作天等假設值）於 [../06-lean-lss/roi-validation.xlsx](../06-lean-lss/roi-validation.xlsx) 透明計算。

> ⚠️ **不要用「資料量 × 倍數」推算效益。** Excel 的 `Ctrl+H`、「移除重複項」、樞紐分析都是**整欄批次操作**，人點的次數不隨列數成長。真正的效益是**品質**與**可規模化**，時間只是其中一項。

---

## 實測發現：手動流程會產生「不會報錯的錯誤」

第一次手動基線測試時，`Ctrl+H` 的空白取代步驟沒有生效，`UPPER()` 修好了大小寫卻**沒有 `TRIM()` 掉前後空白**。結果：

- 樞紐分析把 `"  ENG-001 "` 和 `"ENG-001"` 當成**兩台不同的機台**，每台被拆成兩列
- **Excel 沒有跳出任何錯誤訊息**

本資料集還埋了第二個同類陷阱：`PredictedStatus` 有 `Warning` / `warning` / `WARNING` 三種寫法。手動樞紐會把同一個 KPI **拆成三類**，導致警告數被嚴重低估。

巨集的 `Trim + UCase` 與 `NormalizeStatus` 一次就對，且每次都對。

> 這是 DMAIC 中 **Defects（缺陷浪費）** 的實例：自動化消除的不只是時間，更是這種**靜默的錯誤**。相較於「省下 N 分鐘」，「警告數不再默默少算」是更高價值的效益——漏掉一次警告，代價是一台引擎的非計畫停機。此項列入 [../06-lean-lss/roi-validation.xlsx](../06-lean-lss/roi-validation.xlsx) 的品質效益。

---

## 誠信說明

- 兩個耗時皆為**親自實測**（🟢），非估計值。
- 感測資料、引擎編號、embedding、模型判讀皆為**真實計算結果**；工單號、維護成本、匯出日期為模擬。
- 匯出檔**不含**任何來自 `RUL_FD001` 的真實答案。
- 年度效益需再乘上「每日次數／人數／工作天」等假設值，於 ROI 表透明標註為 🟡。
