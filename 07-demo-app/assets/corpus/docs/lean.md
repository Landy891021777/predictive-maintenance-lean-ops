# 精實改善案與效益驗證

> 🟢 真實專案文件

## 1. 問題定義：兩層浪費

製造與維運現場有兩層浪費，本案兩層都處理，但主從分明：
- 第二層｜流程浪費（主角）：工程師每天手動下載 SAP-style 匯出檔、在 Excel 清理彙整、人工判讀、手動寄報表。
  解法為 VBA 巨集 + Power Automate Desktop（RPA）+ Power BI，效益可實測。
- 第一層｜實體浪費（技術亮點）：設備非計畫停機與過度保養。
  解法為 VAE 異常偵測模型自動判讀健康狀態，效益為情境推估。
方法論：Lean Six Sigma DMAIC（Define、Measure、Analyze、Improve、Control）。

*來源：整理自 06-lean-lss/DMAIC.md 與根目錄 README.md（以最終版本為準）*

## 2. 手動流程與浪費盤點

改善前的手動流程共 7 步：登入 SAP 匯出 CSV → Excel 匯入貼上 → 手動清理髒資料（去空白、去重、補缺）
→ 手動彙整（樞紐分析）→ 人工判讀健康 → 製作報表 → 手動寄 Email。
對應的七大浪費：Motion（反覆下載、複製貼上）、Waiting（等匯出、等彙整）、
Overprocessing（每天重做同樣清理）、Defects（人工修正出錯、判讀主觀）、
Underutilized talent（工程師時間耗在行政作業）。
實測手動完成一次清理彙整需 15 分鐘（碼錶計時）。

*來源：整理自 06-lean-lss/value-stream-map.md 與 02-automation-vba/README.md；15 分鐘為碼錶實測*

## 3. 自動化結果（實測）

VBA 巨集 CleanAndSummarize 一次處理 3 個匯出檔：
- 原始 13,750 列 → 去除重複 654 列 → 乾淨 13,096 列
- 狀態大小寫正規化 2,001 筆，模型 Warning 共 1,693 筆
- 缺 NearestDistance 386 筆、缺 MaintenanceCost 901 筆
耗時兩次實測：Alt+F8 互動執行 1.6 秒、經 Power Automate 觸發 1.844 秒，
相較手動 15 分鐘約快 500 倍（兩次分別為 562 倍與 488 倍）。

*來源：02-automation-vba/README.md 與 03-rpa-power-automate/outbox 報表 Summary 分頁（實測）*

## 4. 手動作業的靜默錯誤

手動流程最大的風險不是慢，而是出錯時 Excel 不會報錯。若直接拿原始匯出檔做樞紐分析、
忘了 TRIM 與統一大小寫：
- 樞紐表會出現 300 台機台（實際只有 100 台），同一台被拆成多列
- 狀態欄出現 6 種寫法（HEALTHY、Healthy、WARNING、Warning、healthy、warning）
- Warning 只數到 1,496 筆，實際為 1,693 筆
建立手動基線時真的發生過：Ctrl+H 的空白取代沒有生效，樞紐分析把前後有空白的機台代號當成另一台，且無任何錯誤訊息。
漏算 Warning 的代價可能是一台引擎的非計畫停機。

*來源：07-demo-app 自動化頁直接對原始匯出檔計算；手動基線事件記錄於 02-automation-vba/README.md*

## 5. ROI 效益試算

實測輸入（🟢）：手動單次 900 秒、自動單次 1.6 秒，單次省時 898.4 秒。
假設輸入（🟡，可替換）：每天 2 次、1 人、每年 240 工作天、人力成本 NT$500/小時、
一次性導入工時 40 小時（含需求釐清、開發、測試、RPA 串接、看板、文件與訓練）。
結果：年省約 120 小時、年省人力成本約 NT$59,893；導入成本 NT$20,000；
首年 ROI 約 199%；回本約 80 個工作天。
唯一的實測值是單次省時；年省工時、ROI、回本天數都建立在使用量假設上。
使用量假設曾由 3 人 × 每天 3 次下修為 1 人 × 每天 2 次，因原假設使 ROI 高達 1,248%，不具可信度。

*來源：06-lean-lss/build_roi.py 與 roi-validation.xlsx（校準版），本段依相同公式重算*

## 6. 維護成本 −84% 與停機時間 −36% 的推導

這兩個數字是情境推估（🟡），不是實測。推導方式為 value-driver 公式，比較公開基準版本與本專案模型：
- 公開基準：推導採用 precision 75%、recall 70%，依據為原始 Kaggle notebook
  （wassimderbel/nasa-predictive-maintenance-rul）的分類段落；該段各模型（SVM、隨機森林、
  Naive Bayes、KNN）在測試集上的 macro precision 約 0.66–0.72、recall 約 0.65–0.71
- 本專案 VAE（Healthy 類實測）：precision 96.4%、recall 80.6%，推導時取整數 96%、81%
  （若以未取整的值計算，兩個降幅分別約為 86% 與 35%）
- 1 − Precision(Healthy)：25% → 4%，代表「判為健康、其實在衰退」的漏判比例下降 84.0%，
  對應非計畫故障造成的維護成本
- 1 − Recall(Healthy)：30% → 19%，代表「其實健康、卻被叫去檢修」的比例下降 36.7%（報告中記為 36%），對應不必要的停機
限制：公開基準是 3 分類（RUL ≤68 / 69–137 / >137）、在 7,221 筆上評估；本專案是 2 分類、
在 100 台引擎的最後一個 cycle 上評估，兩者評估方式不同。公開資料集沒有真實成本資料。

*來源：推導整理自 01-core-model/docs/航太專案 量化效益對比與技術補充.xlsx；Healthy 類指標取自 model_validation.csv*

## 7. Power Automate 流程與誠信聲明

實際採用的 Power Automate Desktop 流程 DailyHealthReport：開啟 Excel 執行無對話框巨集 CleanAndSummarizeSilent
→ 儲存關閉 → 取得當日日期 → 複製報表到 outbox → 重新命名為 DailyHealthReport_yyyyMMdd.xlsm → 桌面通知。
巨集另提供無對話框進入點，因為 RPA 遇到彈窗會卡住等人點擊。
誠信聲明：
- SAP 匯出檔為模擬（格式仿 SAP 匯出的髒資料），本專案未串接真實 SAP 系統
- 「從 SAP 下載」在流程中以複製檔案模擬；分發採存檔加桌面通知，未串接 Email
- Power Apps 僅完成設計稿（個人帳號無法部署）
- 雲端展示網站無法執行 VBA 與 Power Automate，網站上的清理為同一套規則的 Python 重現，已與 RPA 實際產出逐項驗證一致

*來源：03-rpa-power-automate/README.md、screenshots/自動化流程.png、04-powerapps-design/README.md*
