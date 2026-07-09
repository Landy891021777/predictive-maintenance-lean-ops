# Predictive Maintenance Lean Ops 實作計畫

> **給執行者：** 本計畫每個階段附一段「📋 可複製 Prompt」，可貼到新的 Claude Code session 執行（Prompt 自帶背景，不依賴本對話）。GUI 工具（Power BI / Power Automate Desktop / Power Apps）的手動步驟另列。

**Goal:** 把 VAE 航太預測維護專案延伸為 DMAIC 精實營運改善案，整合進 GitHub repo，命中 ASML CS-OPS Data Analyst JD。

**Architecture:** 兩層浪費敘事——流程自動化（VBA/RPA/Power BI）為主角，AI 模型（VAE）為判讀引擎。效益以「實測綠／假設黃」透明 ROI 模型驗證。

**Tech Stack:** Python/PyTorch(既有) · VBA · Power Automate Desktop · Power BI Desktop · Power Apps(設計稿) · Lean/DMAIC

**Repo:** `C:\Users\User\Desktop\predictive-maintenance-lean-ops`

---

## 進度總覽

- [x] **P0** 基礎建置（repo、核心模型、README、規格）— 已完成
- [ ] **P1** Lean 骨架（DMAIC + 價值流圖）
- [ ] **P2** VBA 巨集（清理 SAP 匯出 → 彙整）
- [ ] **P3** RPA（Power Automate Desktop）
- [ ] **P4** Power Apps 設計稿
- [ ] **P5** Power BI 儀表板
- [ ] **P6** ROI 效益驗證
- [ ] **P7** 收尾 + 面試小抄 + 推 GitHub

**依賴：** P0 → P1 →（P2、P3、P4、P5 可平行）→ P6（需 P2 實測數字）→ P7

---

## P1 — Lean 骨架（DMAIC + 價值流圖）

**類型：** 🟢 全部可由 AI 生成
**產出：** `06-lean-lss/DMAIC.md`、`06-lean-lss/value-stream-map.md`

**驗收：**
- DMAIC 五階段完整，Define 清楚定義「第二層流程浪費」
- VSM 標出手動作業的非加值步驟與等待時間
- 只用可溯源的資料，假設值明確標註

### 📋 可複製 Prompt（P1）

```
我在做一個求職作品集專案，位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
請先讀 docs/superpowers/specs/2026-07-09-predictive-maintenance-lean-ops-design.md 了解完整背景。

背景重點：這是把一個 NASA CMAPSS + VAE 預測維護 AI 專案，包裝成 DMAIC 精實營運改善案，
目標職缺是 ASML CS-OPS Data Analyst（Lean 營運自動化職）。
核心定調是「兩層浪費」：第二層流程浪費（工程師手動下載SAP→Excel彙整→人工判讀→手動寄報表）
是主角，第一層實體浪費（設備停機，由VAE模型解決）是技術亮點。

請幫我在 06-lean-lss/ 產出兩份中文文件：
1. DMAIC.md — 完整 DMAIC 五階段：
   - Define：定義流程浪費問題、專案範圍、改善目標
   - Measure：列出要量測的基線指標（手動作業工時、步驟數、錯誤率），
     工時用「假設基線+待實測」方式呈現，並標註哪些之後會由P2 VBA實測填入
   - Analyze：用7大浪費(TIMWOODS)分析手動流程，指出根因
   - Improve：對應 VBA/RPA/PowerBI/PowerApps 各自消除哪個浪費
   - Control：PowerBI HK分層看板持續監控、異常自動通知
2. value-stream-map.md — 手動 vs 自動化的價值流圖（用文字/表格/mermaid呈現current state與future state），
   標出每步驟的處理時間、等待時間、加值/非加值。

誠信原則：不捏造數字，假設值標🟡、實測待填標「(P2實測)」。
完成後 git add 並 commit（訊息用中文，說明P1完成）。
```

---

## P2 — VBA 巨集（清理 SAP 匯出 → 自動彙整）

**類型：** 🟢 AI 生成 VBA 原始碼 + 模擬資料；🟡 你在 Excel 手動匯入巨集並實測計時
**產出：** `02-automation-vba/sample-data/*.csv`（模擬髒 SAP 匯出）、`02-automation-vba/src/*.bas`、`02-automation-vba/README.md`

**驗收：**
- 巨集能讀模擬 SAP 匯出、清理髒資料、產出彙整報表分頁
- README 記錄「手動做一次的耗時 vs 巨集耗時」（實測）
- 巨集內用 `Timer` 印出執行秒數，供實測

### 📋 可複製 Prompt（P2）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
先讀 docs/superpowers/specs/2026-07-09-predictive-maintenance-lean-ops-design.md。

請幫我在 02-automation-vba/ 建立一個「取代手動SAP資料整理」的VBA自動化：

1. sample-data/：產生2~3個模擬「SAP匯出」的CSV檔（用Python腳本生成，欄位模擬感測器/工單資料，
   刻意加入髒資料：多餘空白、日期格式不一、重複列、缺值、千分位逗號數字）。
   同時附上生成腳本 generate_sample_data.py。
2. src/CleanAndSummarize.bas：VBA巨集，功能=
   - 匯入 sample-data 的 CSV
   - 清理（去空白/去重複/統一日期/補缺值標記/轉數字）
   - 產出「彙整報表」分頁（依機台/日期彙總健康指標與異常數）
   - 用 Timer 記錄並在完成訊息顯示執行秒數
   - 程式碼加中文註解說明每段對應消除哪個浪費
3. README.md：
   - 巨集安裝與執行步驟（如何匯入.bas、如何跑）
   - 一張「手動流程 vs VBA流程」對照表（步驟數、耗時欄位先留白待我實測填入）
   - 說明這對應JD哪句（replace manual download from SAP, manual summary in excel）

我的環境：個人版Microsoft Office，Windows 11。
完成後git commit。並在最後告訴我：我需要手動做哪些事來實測「手動耗時」與「巨集耗時」。
```

**🟡 你手動要做：** 開 Excel → 匯入 `.bas` → 跑巨集 → 記錄巨集秒數；再手動做一次同樣整理、碼錶計時 → 把兩個數字填回 README 對照表。

---

## P3 — RPA（Power Automate Desktop）

**類型：** 🟡 主要你手動在 Power Automate Desktop 建流程；🟢 AI 生成流程設計文件、截圖清單、README
**產出：** `03-rpa-power-automate/README.md`、`flow-export/`（流程匯出檔）、`screenshots/`（你截圖）

**驗收：**
- 流程設計文件描述「自動抓檔 → 觸發VBA/彙整 → 自動寄報表」的每個動作
- README 有截圖占位與說明，對應 JD「replace manual sending reports by email」

### 📋 可複製 Prompt（P3）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
先讀規格 docs/superpowers/specs/2026-07-09-predictive-maintenance-lean-ops-design.md
以及 02-automation-vba/README.md。

Power Automate Desktop（Windows 11內建免費）不能由CLI建立，所以請幫我：
1. 03-rpa-power-automate/README.md：寫一份「RPA流程設計書」，描述我要在Power Automate Desktop
   手動建立的每個動作步驟（繁體中文），流程=
   - 定時/手動觸發
   - 從指定資料夾抓取「SAP匯出」CSV（模擬情境）
   - 呼叫Excel執行P2的清理彙整巨集
   - 將彙整報表以Email寄出（或存到指定資料夾）
   每步驟寫清楚用哪個Power Automate action、參數設定。
2. 列一份「截圖清單」：我建好流程後該截哪幾張圖放進screenshots/。
3. 說明這對應JD哪句，以及RPA消除的浪費（Motion/Waiting）。
完成後git commit。

最後用條列告訴我：在Power Automate Desktop裡我要照著做的手動操作順序（給我一步步教學）。
```

**🟡 你手動要做：** 依教學在 Power Automate Desktop 建流程 → 匯出流程檔放 `flow-export/` → 截圖放 `screenshots/`。

---

## P4 — Power Apps 設計稿（線框圖 + 規格）

**類型：** 🟡 個人帳號無法真建 App → 🟢 AI 生成線框圖(SVG)+畫面規格
**產出：** `04-powerapps-design/wireframes/*.svg`、`04-powerapps-design/README.md`

**驗收：**
- 線框圖呈現「現場人員輸入感測值 → 查詢引擎健康」的主要畫面
- 規格說明資料流、與 VAE 模型串接概念、若在公司 tenant 如何實作

### 📋 可複製 Prompt（P4）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
先讀規格與 01-core-model/docs/VAE_MCP_專案說明.md（了解VAE模型輸入輸出）。

個人版Microsoft帳號無法真的建Power Apps，所以做「設計稿」。請在 04-powerapps-design/ 產出：
1. wireframes/：用SVG畫2~3個手機/平板App線框圖畫面：
   - 畫面1：現場人員輸入21個感測器數值（或選機台）
   - 畫面2：顯示健康判讀結果（Healthy/Warning、潛空間距離、行動建議）——對應VAE模型輸出
   - 畫面3：歷史健康趨勢列表
2. README.md（繁中）：
   - 每個畫面的用途、欄位、按鈕、資料來源
   - 資料流：App → (概念上呼叫)VAE推論 → 回傳健康狀態
   - 「若在ASML公司tenant如何實作」：用Power Apps + 自訂連接器接VAE API + Dataverse儲存
   - 誠實標註：本階段為設計稿，因個人帳號限制未實際部署
   - 對應JD哪句（solutions developer, PowerAPPS）
完成後git commit。
```

---

## P5 — Power BI 儀表板

**類型：** 🟡 你在 Power BI Desktop 建報表；🟢 AI 生成資料、量測定義、版面設計、README
**產出：** `05-powerbi-dashboard/dashboard.pbix`（你存）、`sample-data`、`screenshots/`、`README.md`

**驗收：**
- 儀表板含 KPI 卡、健康趨勢圖、HK 三層分層看板概念
- README 說明每個視覺對應的量測與 JD 關鍵字（PowerBI, HK BI, dashboard）

### 📋 可複製 Prompt（P5）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
先讀規格文件。

Power BI Desktop需手動建.pbix，請幫我準備好一切讓我照著拉：
1. 產生 05-powerbi-dashboard/ 用的模擬資料CSV（Python腳本），欄位含：
   日期、機台ID、健康分數、異常flag、維護成本、停機時數、手動作業工時等，
   足以支撐KPI與趨勢圖。附生成腳本。
2. README.md（繁中）「儀表板建置指南」：
   - 版面設計：Tier1(高層KPI卡:成本↓/停機↓/自動化省時)、
     Tier2(部門健康趨勢/異常分佈)、Tier3(現場機台明細) —— 對應Hoshin Kanri分層
   - 每個視覺用哪個圖表類型、放哪些欄位、需要的DAX量值（寫出DAX公式）
   - 截圖清單
   - 對應JD（PowerBI, HK BI dashboard, digital measurement）
3. 若可行，附一個.pbit範本說明或pbix建置的逐步操作。
完成後git commit。最後給我在Power BI Desktop裡的一步步操作教學。
```

**🟡 你手動要做：** 依教學在 Power BI Desktop 建報表 → 存 `dashboard.pbix` → 截圖放 `screenshots/`。

---

## P6 — ROI 效益驗證

**類型：** 🟢 AI 生成 xlsx 模型（需 P2 實測數字；未實測前先用假設，之後替換）
**產出：** `06-lean-lss/roi-validation.xlsx`

**驗收：**
- 假設為明確輸入格、ROI 為公式函數
- 實測綠🟢 / 假設黃🟡 分色；兩層效益分列
- 每格可溯源

### 📋 可複製 Prompt（P6）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
先讀規格文件第3節（效益計算方法）與 02-automation-vba/README.md（取實測省時數字，若尚未實測就用假設並標註）。

請用Python(openpyxl)產生 06-lean-lss/roi-validation.xlsx，一個透明ROI模型：
- 「輸入假設」區：每次手動耗時(實測🟢)、每次自動耗時(實測🟢)、每天執行次數(假設🟡)、
  使用人數(假設🟡)、年工作天(假設🟡)、人力成本/小時(假設🟡)、開發投入工時(實測🟢)
- 「計算結果」區(公式)：每次省時、年省工時、年省人力成本、回收期、首年ROI%
- 實測格填綠底、假設格填黃底，並在旁註明資料來源
- 第二區「第一層AI效益」分開列：維護成本↓84%、停機↓36%、Precision+21%，
  全標「情境假設(公開資料集)」
- 頂部放一段誠信聲明：綠=實測、黃=假設可替換
用真實可用的Excel公式(不是寫死數字)。完成後git commit。
```

---

## P7 — 收尾 + 面試小抄 + 推 GitHub

**類型：** 🟢 AI 生成小抄、更新 README；🟡 你/AI 一起推 GitHub
**產出：** `docs/interview-cheatsheet.md`、更新 `README.md` 進度與截圖、GitHub 遠端

**驗收：**
- STAR 面試小抄對齊 ASML JD 六大關鍵字
- README 進度全勾、嵌入關鍵截圖
- repo 成功推上 GitHub

### 📋 可複製 Prompt（P7）

```
專案位置：C:\Users\User\Desktop\predictive-maintenance-lean-ops
讀規格文件與所有階段的README。

1. 產出 docs/interview-cheatsheet.md（繁中STAR面試小抄），針對ASML CS-OPS Data Analyst：
   - 2分鐘自我介紹（扣兩層浪費故事）
   - 針對JD六大關鍵字(Lean/LSS, VBA, PowerAutomate, PowerApps, PowerBI, ROI)各一個STAR小故事
   - 3個可能被問的技術/情境題與答法
   - 誠信提醒：哪些是實測、哪些是設計稿/假設，被問到如何誠實回答
2. 更新根 README.md：把進度checkbox勾完、嵌入各階段代表截圖(用相對路徑)。
3. git commit。
4. 教我把repo推上GitHub：因為沒裝gh CLI，給我兩條路——
   (A)裝GitHub CLI後gh repo create的指令；(B)在GitHub網頁手動建repo後git remote add + push的完整指令。
```

**🟡 你手動要做：** 在 GitHub 建 repo（網頁或裝 gh）→ 依指令 `git remote add` + `git push`。

---

## Self-Review 檢查（對照規格）

- ✅ 規格六大 JD 關鍵字皆有對應階段（Lean→P1、VBA→P2、PowerAutomate→P3、PowerApps→P4、PowerBI→P5、ROI→P6）
- ✅ 兩層浪費定調貫穿 P1/P6
- ✅ 誠信原則（實測/假設分色）在 P1/P2/P6 明確要求
- ✅ 個人帳號限制在 P4/P5 誠實處理
- ✅ 每階段附自帶背景的可複製 Prompt + 手動步驟界線
