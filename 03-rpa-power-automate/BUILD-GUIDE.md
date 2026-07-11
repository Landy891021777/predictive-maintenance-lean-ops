# P3 建置教學 — Power Automate Desktop 逐格點擊

> 目標：建一條機器人流程，自動「抓 SAP 匯出檔 → 跑 Excel 巨集清理彙總 → 輸出報表」。
> 環境：Windows 11 內建的 Power Automate（免費，個人 Microsoft 帳號可用）。
> 預估時間：30–45 分鐘。

---

## 開始前的檢查清單

- [ ] `02-automation-vba\CleanAndSummarize.xlsm` 已存在，且已匯入最新 `.bas`、編譯通過
- [ ] 在 Excel 手動跑過 `CleanAndSummarizeSilent` 一次，確認**不跳對話框**、能跑完
- [ ] **關閉** Excel（不要讓 `.xlsm` 開著，否則機器人開檔會被鎖住）
- [ ] 路徑變數先記好：
  `C:\Users\User\Desktop\predictive-maintenance-lean-ops`

---

## 步驟 0：開啟 Power Automate 並建立流程

1. 開始功能表搜尋 **Power Automate** → 開啟（第一次會要你用**個人 Microsoft 帳號**登入）
2. 主畫面點 **`+ 新建流程`（New flow）**
3. 流程名稱輸入 `DailyHealthReport` → **建立**
4. 進入流程設計器：左邊是**動作面板**（有搜尋框），中間是**畫布**，右邊是變數區

> 加動作的方式：在左側搜尋框打動作名稱 → **拖到畫布**（或雙擊）→ 跳出參數視窗 → 填完按**儲存**。

---

## 核心流程（3 個動作，先讓它會跑）

### 動作 1：啟動 Excel 並開啟活頁簿
- 搜尋 **`啟動 Excel`（Launch Excel）** → 拖入
- 參數：
  - **啟動 Excel**：選「**並開啟後續文件**（and open the following document）」
  - **文件路徑**：按資料夾圖示選
    `...\predictive-maintenance-lean-ops\02-automation-vba\CleanAndSummarize.xlsm`
  - **使執行個體可見**：先開 **是（Yes）**（方便你看它動作；之後可改 No）
  - **以唯讀方式開啟**：**否（No）**（巨集要寫入分頁）
  - 產生變數：`%ExcelInstance%`（預設，不用改）
- **儲存**

### 動作 2：執行 Excel 巨集
- 搜尋 **`執行 Excel 巨集`（Run Excel macro）** → 拖到動作 1 下方
- 參數：
  - **Excel 執行個體**：`%ExcelInstance%`
  - **巨集**：輸入 `CleanAndSummarizeSilent`（一字不差，注意大小寫）
- **儲存**

> 這一步就是「用巨集取代手動 Excel 作業」的核心。巨集內已 `ThisWorkbook.Save`。

### 動作 3：關閉 Excel
- 搜尋 **`關閉 Excel`（Close Excel）** → 拖到最下方
- 參數：
  - **Excel 執行個體**：`%ExcelInstance%`
  - **關閉 Excel 前**：選「**儲存文件**（Save document）」
- **儲存**

### ▶ 先跑這 3 個動作
- 畫布上方按 **執行（Run）**
- 應該看到 Excel 自動開啟 → 閃一下（跑巨集）→ 自動關閉
- 打開 `.xlsm` 檢查 `Summary` 分頁的 `B9`（Elapsed seconds）有被更新 → 成功！

> **若卡住**：最常見是 Excel 已經開著那個檔（檔案鎖）→ 關掉所有 Excel 再跑。
> 或巨集安全性擋住 → Excel 設定「信任中心 → 巨集設定」暫時放寬，或把資料夾設為信任位置。

---

## 加值段 A：模擬「從 SAP 下載」（放在動作 1 之前）

讓機器人先去「抓檔」，故事更完整（對應 JD 的 replace manual download from SAP）。

### 動作 A1：取得資料夾中的檔案
- 搜尋 **`取得資料夾中的檔案`（Get files in folder）** → 拖到**最上面**
- 參數：
  - **資料夾**：`...\02-automation-vba\sample-data\lifecycle`
  - **檔案篩選**：`SAP_EXPORT_*.csv`
  - **包含子資料夾**：否
  - 產生變數：`%Files%`
- **儲存**

### 動作 A2：For each 迴圈 + 複製檔案
- 搜尋 **`For each`** → 拖到 A1 下方
  - **要逐一查看的值**：`%Files%`
  - 儲存項目至：`%CurrentItem%`
- 在 For each 的 **迴圈內**（拖進 For each 和 End 之間）加 **`複製檔案`（Copy file(s)）**：
  - **要複製的檔案**：`%CurrentItem%`
  - **目的地資料夾**：`...\03-rpa-power-automate\inbox`
  - **如果檔案存在**：覆寫（Overwrite）
- **儲存**

---

## 加值段 B：輸出當日報表到 outbox（放在動作 3 之後）

### 動作 B1：取得目前日期時間
- 搜尋 **`取得目前日期與時間`（Get current date and time）** → 產生 `%CurrentDateTime%`

### 動作 B2：將日期時間轉換為文字
- 搜尋 **`將日期時間轉換為文字`（Convert datetime to text）**
  - **要轉換的日期時間**：`%CurrentDateTime%`
  - **要使用的格式**：自訂 → `yyyyMMdd`
  - 產生 `%FormattedDateTime%`

### 動作 B3：複製檔案到 outbox
- 搜尋 **`複製檔案`（Copy file(s)）**
  - **要複製的檔案**：`...\02-automation-vba\CleanAndSummarize.xlsm`
  - **目的地資料夾**：`...\03-rpa-power-automate\outbox`
  - 複製後可用「**重新命名已複製的檔案**」選項，或改用「**移動並重新命名檔案**」：
    命名為 `DailyHealthReport_%FormattedDateTime%.xlsm`
  - 如果檔案存在：覆寫

### 動作 B4：桌面通知（取代手動確認）
- 搜尋 **`顯示通知`（Display notification）** 或 **`顯示訊息`（Display message）**
  - 標題：`報表完成`
  - 訊息：`DailyHealthReport 已產生於 outbox`

---

## 加值段 C（選配）：自動寄 Email（需本機 Outlook）

> 沒有安裝 Outlook 桌面版就跳過，用加值段 B 的「存檔 + 通知」即可達到「免手動寄送」。

- 搜尋 **`啟動 Outlook`（Launch Outlook）** → `%OutlookInstance%`
- 搜尋 **`從 Outlook 傳送電子郵件訊息`（Send email through Outlook）**
  - 帳戶：你的信箱
  - 收件者：主管信箱（Demo 用可填自己）
  - 主旨：`每日設備健康報表 %FormattedDateTime%`
  - 本文：`附件為今日 100 台引擎的健康彙總（模型判讀 + VBA 自動彙總）。`
  - 附件：`...\03-rpa-power-automate\outbox\DailyHealthReport_%FormattedDateTime%.xlsm`

---

## 最終動作順序（完整版）

```
A1  取得資料夾中的檔案（lifecycle 的 SAP_EXPORT_*.csv）
A2  For each → 複製檔案到 inbox
1   啟動 Excel（開 CleanAndSummarize.xlsm）
2   執行 Excel 巨集（CleanAndSummarizeSilent）
3   關閉 Excel（儲存）
B1  取得目前日期時間
B2  轉成文字 yyyyMMdd
B3  複製報表到 outbox（含日期）
B4  顯示通知
[C  選配：Outlook 寄出]
```

---

## 排程（選配，模擬「每天自動跑」）

Power Automate Desktop 個人版沒有雲端排程，用 Windows 內建的**工作排程器**：
1. 開始搜尋「**工作排程器**」→ 建立基本工作
2. 觸發：每天 08:00
3. 動作：啟動程式 → `PAD.Console.Host.exe`（或用 PAD 內的「以指令列執行」提供的指令）
   → 附加參數指定流程名稱 `DailyHealthReport`
4. （簡單替代：Demo 時直接在 PAD 手動按執行即可，面試說明「可掛工作排程器每日觸發」）

---

## 📸 完成後截圖（放 screenshots/）

- [ ] 整條流程的動作清單總覽
- [ ] 「執行 Excel 巨集 = CleanAndSummarizeSilent」動作設定
- [ ] 執行成功的畫面（或執行紀錄綠勾）
- [ ] `inbox/` 有被複製進來的 CSV
- [ ] `outbox/` 產生的 `DailyHealthReport_YYYYMMDD.xlsm`
- [ ]（若做）通知彈窗 或 寄出的 Email

截好後告訴我，我會在 P7 把這些截圖嵌進 README。
