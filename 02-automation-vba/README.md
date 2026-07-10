# P2 — VBA 巨集：取代手動 SAP 資料清理與彙整

> **對應 ASML JD：** *"use macro to replace manual download from SAP, manual summary in excel"*
> **消除的浪費：** Motion（反覆匯入貼上）、Overprocessing（每天重做同樣清理）、Defects（人工修髒資料出錯）

---

## 資料來源與誠信聲明

`sample-data/` 的 3 個 CSV 由 [`generate_sample_data.py`](sample-data/generate_sample_data.py) 從**真實的 NASA CMAPSS FD001 資料集**產生，並包裝成「SAP 匯出檔」的樣貌。

| 欄位 | 真實 / 模擬 | 說明 |
|------|------------|------|
| `EquipmentID` | 🟢 **真實** | 100 台引擎的真實 unit 編號（ENG-001 ~ ENG-100） |
| `Cycle` | 🟢 **真實** | 真實運轉週期 |
| `Sensor_2 … Sensor_17`（12 欄） | 🟢 **真實** | 真實感測器量測值，對齊 [01-core-model](../01-core-model/) 的特徵選擇 |
| `HealthScore` | 🟢 **真實推導** | 由真實 RUL 計算：`min(RUL, 125) / 125` |
| `AnomalyFlag` | 🟢 **真實推導** | 由真實退化判定：`RUL ≤ 30` |
| `ExportDate` | 🟡 模擬 | 假設分 3 天批次匯出 |
| `Timestamp` | 🟡 模擬 | 由 Cycle 推導 |
| `WorkOrder` | 🟡 模擬 | CMAPSS 無此欄位（屬 SAP/ERP 側） |
| `MaintenanceCost` | 🟡 模擬 | CMAPSS 無此欄位（屬 SAP/ERP 側） |

**刻意加入的髒資料**（模擬真實 SAP 匯出的品質問題，非資料集本身的問題）：

| 髒資料類型 | 比例 | 實際筆數（單檔） |
|-----------|------|----------------|
| `EquipmentID` 前後空白 | 15% | 1,058 |
| `EquipmentID` 小寫 | 10% | 716 |
| `ExportDate` 三種格式混用 | 100% | `2026/07/01`、`01-Jul-2026`、`2026-07-01` |
| `MaintenanceCost` 千分位逗號 | ~40% | 1,692 |
| `MaintenanceCost` 缺值 | 7% | 483 |
| `HealthScore` 缺值 | 5% | — |
| 重複列 | 5% | 343 |

**資料規模：** 3 檔 × 7,220 列 = **21,660 原始列 → 去重後 20,631 列**（100 台引擎）

> **為何用分號 `;` 分隔？** SAP 匯出常用分號，且能讓千分位逗號 `1,234.56` 不破壞欄位——這是真實情境的設計選擇。
>
> **為何 `.bas` 的註解是英文？** VBA 編輯器匯入 `.bas` 時以系統 ANSI 編碼（繁中 Windows 為 Big5）讀取，若檔案含 UTF-8 中文會變亂碼並導致**編譯錯誤**。因此程式碼保持純 ASCII，中文詳解一律放在本 README。這同時符合 JD 的 business English 要求。

---

## 這個巨集做什麼

把「手動 7 步」變成「一鍵」：

| 手動流程 | 巨集自動做 |
|----------|-----------|
| 逐一開啟 3 個 CSV | 自動掃描 `sample-data/` 讀取全部 `.csv` |
| 去除機台代號前後空白、統一大小寫 | `Trim` + `UCase` |
| 統一 3 種混用的日期格式 | `NormalizeDate()` 解析 `yyyy/mm/dd`、`yyyy-mm-dd`、`dd-Mon-yyyy` |
| 手動找出並刪除重複列 | 以「日期\|機台\|Cycle\|時戳\|工單」為鍵去重 |
| 千分位數字 `1,234.56` 轉數值 | `CleanNumber()` |
| 標記缺值 | 統計 `HealthScore` / `MaintenanceCost` 缺值筆數 |
| 樞紐分析做機台彙總 | 自動產生 `Summary` 分頁（筆數／平均健康／異常次數／異常率／成本合計） |

**額外：** 巨集內建 `Timer`，執行完顯示**實測耗時（秒）**並寫入 `Summary!B8` — 這是 P6 ROI 表的 🟢 實測輸入值。

---

## 檔案

| 檔案 | 說明 |
|------|------|
| `sample-data/generate_sample_data.py` | 從真實 CMAPSS 產生模擬 SAP 匯出檔 |
| `sample-data/SAP_EXPORT_2026070*.csv` | 3 個模擬匯出檔，各 7,220 列 × 20 欄 |
| `src/CleanAndSummarize.bas` | VBA 巨集原始碼 |

### 重新產生模擬資料
```bash
py -3 sample-data/generate_sample_data.py
```
（亂數種子固定為 42，結果可重現。需要 `C:\Users\User\Desktop\kaggle 專案\nasa專案\train_FD001.txt`）

---

## 安裝與執行

1. 開啟 Excel → 新增空白活頁簿 → **另存為「Excel 啟用巨集的活頁簿 (.xlsm)」**，存到本資料夾 `02-automation-vba\` 底下（巨集靠這個位置自動找到 `sample-data`）。
2. 按 `Alt + F11` 開啟 VBA 編輯器。
3. 功能表 **檔案 → 匯入檔案** → 選 `src\CleanAndSummarize.bas`。
4. **偵錯 → 編譯 VBAProject**（沒跳視窗＝通過）。
5. `Alt + Q` 回 Excel → `Alt + F8` → 選 `CleanAndSummarize` → **執行**。

預期結果：
```
Files read             : 3
Raw rows read          : 21660
Duplicate rows removed : 1029
Clean rows             : 20631
ELAPSED: ?.??? seconds
```

> 若巨集找不到 `sample-data`，會跳出資料夾選擇視窗讓你手動指定。

---

## 效益量測：手動 vs 自動（待實測填入）

| 項目 | 手動流程 | VBA 自動流程 |
|------|---------|-------------|
| 步驟數 | 7 步 | 1 步（一鍵） |
| 單次耗時 | **______ 分鐘** 🟢 | **______ 秒** 🟢 |
| 處理列數 | 21,660 | 21,660 |
| 重複列處理 | 人工比對，易漏 | 自動去除 1,029 筆 |
| 日期格式統一 | 人工逐欄改 | 自動 |
| 缺值標記 | 人工檢查 | 自動統計 |
| **正確性** | **易出錯（見下）** | 規則固定，可重現 |

### 如何量測

**自動耗時：** 執行巨集後訊息框直接顯示（也寫在 `Summary!B8`）。

**手動耗時：** 碼錶計時，實際手工做一次完整流程（開檔 → 資料剖析 → 清 ID → 統一日期 → 移除重複 → 轉數值 → 樞紐分析）。**卡住與重做的時間也要算進去**，那正是真實成本。

---

## 實測發現：手動流程會產生「不會報錯的錯誤」

第一次手動基線測試時，`Ctrl+H` 的空白取代步驟沒有生效，`UPPER()` 修好了大小寫卻**沒有 `TRIM()` 掉前後空白**。結果：

- 樞紐分析把 `"  ENG-001 "` 和 `"ENG-001"` 當成**兩台不同的機台**
- 每台機台被拆成兩列，主管看到的「ENG-001 有 114 筆」實際少算了約 **17%**（正是資料中帶空白的比例）
- **Excel 沒有跳出任何錯誤訊息**

巨集的 `Trim + UCase` 一次就對，且每次都對。

> 這是 DMAIC 中 **Defects（缺陷浪費）** 的實例：自動化消除的不只是時間，更是這種**靜默的錯誤**。相較於「省下 N 分鐘」，「報表不再默默算錯」往往是更高價值的效益 —— 此項列入 [../06-lean-lss/roi-validation.xlsx](../06-lean-lss/roi-validation.xlsx) 的品質效益。

---

## 誠信說明

- 兩個耗時皆為**親自實測**（🟢），非估計值。
- 感測資料、引擎編號、健康分數、異常標記皆來自**真實 NASA CMAPSS**；工單號、維護成本、匯出日期為模擬（見上方對照表）。
- 年度效益需再乘上「每日次數／人數／工作天」等假設值，於 ROI 表透明標註為 🟡。
