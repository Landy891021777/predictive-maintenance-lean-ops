# P3 — RPA：Power Automate Desktop 自動化流程

> **對應 ASML JD：** *"use macro to replace manual download from SAP, manual sending reports by email"* · *"Automation enabler"*
> **消除的浪費：** Motion（手動下載/搬檔/寄信）、Waiting（等人來觸發下一步）
> **工具：** Power Automate Desktop（Windows 11 內建，免費）

---

## 這一步在整條資料流的位置

```
[01] VAE 模型判讀 → model_predictions.csv
        ↓ 包裝成 SAP 匯出檔
[02] sample-data/lifecycle/SAP_EXPORT_*.csv
        ↓ ★ 本階段：Power Automate Desktop 機器人
        ┌─────────────────────────────────────────────┐
        │ 1. 定時/手動觸發                              │
        │ 2. 從「SAP 下載區」搬檔到 inbox（模擬下載）   │
        │ 3. 開 Excel、跑巨集 CleanAndSummarizeSilent   │
        │ 4. 把彙總報表另存到 outbox                    │
        │ 5. 用 Outlook 自動寄出（或存檔通知）          │
        └─────────────────────────────────────────────┘
        ↓
   維運主管收到每日報表，完全不需人工操作
```

**關鍵設計**：巨集提供**無對話框的進入點** `CleanAndSummarizeSilent`（見 [../02-automation-vba/src/CleanAndSummarize.bas](../02-automation-vba/src/CleanAndSummarize.bas)）。因為 RPA 遇到彈窗會卡住等人點——這是把「人工巨集」升級成「無人流程」時的真實工程細節。

---

## 為何是「設計書 + 教學」而非可匯入檔

Power Automate Desktop 的流程**必須在 GUI 裡手動建立**，無法用程式產生。因此本資料夾提供：
1. 這份**流程設計書**（每個動作、參數）
2. 你建好後的**流程匯出檔**（放 `flow-export/`）與**截圖**（放 `screenshots/`）

---

## 資料夾

| 資料夾 | 用途 |
|--------|------|
| `inbox/` | 機器人把 SAP 匯出檔搬進來的落地點（模擬「從 SAP 下載到本機」） |
| `outbox/` | 機器人輸出彙總報表的地方 |
| `flow-export/` | 你在 Power Automate Desktop 建好後，匯出的流程檔 |
| `screenshots/` | 流程截圖 |

---

## 流程設計（Power Automate Desktop 逐動作）

> 變數 `%RepoPath%` = `C:\Users\User\Desktop\predictive-maintenance-lean-ops`

| # | 動作（Action） | 主要參數 | 對應消除的浪費 |
|---|----------------|----------|---------------|
| 1 | **設定變數** `RepoPath` | `C:\Users\User\Desktop\predictive-maintenance-lean-ops` | — |
| 2 | **資料夾 → 取得資料夾中的檔案** | 資料夾 `%RepoPath%\02-automation-vba\sample-data\lifecycle`，篩選 `SAP_EXPORT_*.csv` → 產出 `%Files%` | Motion |
| 3 | **迴圈 For each** `%File%` in `%Files%` | | |
| 4 | ↳ **檔案 → 複製檔案** | 從 `%File%` 到 `%RepoPath%\03-rpa-power-automate\inbox` | Motion（取代手動下載/搬檔） |
| 5 | **Excel → 啟動 Excel** | 開啟現有文件 `%RepoPath%\02-automation-vba\CleanAndSummarize.xlsm`，設為**可見=False**、**唯讀=False** | — |
| 6 | **Excel → 執行 Excel 巨集** | 巨集名稱 `CleanAndSummarizeSilent` | Overprocessing（自動清理彙總） |
| 7 | **Excel → 關閉 Excel** | 儲存文件（巨集內已 `ThisWorkbook.Save`，此處確保關閉） | — |
| 8 | **檔案 → 複製檔案** | 把 `CleanAndSummarize.xlsm` 另存到 `%RepoPath%\03-rpa-power-automate\outbox\每日健康報表_%當日日期%.xlsm` | Motion |
| 9 | **（擇一）Outlook → 傳送電子郵件訊息** | 收件者=主管、主旨「每日設備健康報表」、附件=outbox 檔 | Motion（取代手動寄信） |
| 9' | **（無 Outlook 時替代）顯示通知** | 「報表已產生於 outbox」 | Waiting |

### 觸發方式（擇一）
- **手動**：Power Automate Desktop 裡按執行（Demo 用）
- **排程**：用 Windows「工作排程器」每天早上 08:00 觸發此流程（模擬每日自動跑）

---

## 建置教學（一步步）

1. 開始功能表搜尋 **Power Automate**（Windows 11 內建；沒有就從 Microsoft Store 免費安裝）
2. 登入你的**個人 Microsoft 帳號** → **新建流程（New flow）** → 命名 `DailyHealthReport`
3. 左側動作面板，依上表 1→9 把動作**拖進中間畫布**，逐一填參數
   - 「執行 Excel 巨集」找不到？先確認第 5 步的 Excel 啟動有指到 `.xlsm`，且**巨集已匯入**（見 P2）
4. 上方 **執行（Run）** 測試整條流程
5. 成功後：**選單 → 匯出**（若版本支援）把流程存到 `flow-export/`；或用「**複製**」把所有動作**貼成文字**存成 `flow-export/DailyHealthReport.txt`
6. 依下方清單截圖，存到 `screenshots/`

### 📸 截圖清單
- [ ] 整條流程的動作總覽
- [ ] 「執行 Excel 巨集 = CleanAndSummarizeSilent」的動作設定
- [ ] outbox 裡自動產生的報表檔
- [ ] （若做 Email）寄出的郵件 or 收件匣
- [ ] （若做排程）Windows 工作排程器的設定

---

## 實際採用版本（As-built）

本次實作的流程為：**取檔 → 開 Excel → 跑 `CleanAndSummarizeSilent` → 關檔存檔 → 產出當日報表到 `outbox\DailyHealthReport_YYYYMMDD.xlsm` → 桌面通知**。

已驗證：機器人觸發後，`CleanAndSummarize.xlsm` 的 `Summary` 分頁正確產生（Clean rows 13,096、Total WARNING 1,693、100 台彙總），且 `outbox` 出現當日報表檔。

> **Email 步驟**：設計書保留了 Outlook / Gmail SMTP 兩種寄信方案（見下與 BUILD-GUIDE.md）。本次改採「**存檔 + 桌面通知**」達成同樣的「免手動寄送」效果——正式環境可再接 SMTP 或 Teams 推送。誠實說明：Outlook 桌面版接 Gmail 遇到自動探索問題，故未採用 Email 路線。

## 誠信說明

- Power Automate Desktop 為 Windows 11 免費內建，個人帳號可用；本流程**已實際執行並驗證**。
- 「從 SAP 下載」以「從 lifecycle 資料夾複製檔案到 inbox」模擬——因為沒有真實 SAP 連線。真實環境會改用 SAP GUI Scripting 或 SAP 連接器，流程骨架相同。
- 分發採「存檔 + 桌面通知」；Email 為可選延伸（設計書已備）。
