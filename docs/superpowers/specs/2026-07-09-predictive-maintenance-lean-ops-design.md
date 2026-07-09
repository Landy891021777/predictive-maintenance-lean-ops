# 設計規格：Predictive Maintenance Lean Ops（ASML CS-OPS 延伸專案）

- **日期**：2026-07-09
- **作者**：黃昱霖（Landy Huang）／協作：Claude Code
- **目標職缺**：ASML — CS - OPS team Data Analyst（Hsinchu, Hybrid）
- **狀態**：設計已確認，待轉入 writing-plans

---

## 1. 目的與背景

現有的航太預測維護專案（NASA CMAPSS + VAE + MCP）是一個**深度學習/AI 專案**。但 ASML 這個職缺本質是 **Lean 精實營運 + 辦公室自動化**的 Data Analyst 角色，JD 主打：

- Lean / LSS / Hoshin Kanri（方針管理，HK BI）
- VBA、PowerAutomate、PowerAPPS、PowerBI、SAP 自動化
- 取代「手動下載 SAP → Excel 彙整 → Email 寄報表」的人工作業
- ROI / benefit validation（效益驗證與視覺化）
- Change agent、訓練他人、跨層溝通

**本專案的目的**：把既有 AI 專案「包裝並延伸」成一個 **DMAIC 精實營運改善案**，證明候選人能把一個分析模型落地成「現場每天在用、能省人工、能算 ROI」的自動化系統，精準命中 JD。

**整合形式**：新建單一 GitHub repo `predictive-maintenance-lean-ops`，把原始 VAE 核心與精實延伸整合，用分階段資料夾呈現。文件**中文為主**。

---

## 2. 核心定調：兩層浪費（不可混淆）

| 層 | 浪費類型 | 由誰消除 | 對應 Lean 浪費 | 指標性質 |
|----|---------|---------|---------------|---------|
| **第一層** 營運/實體浪費 | 設備非計畫停機、過度保養、待機 | VAE 預測維護模型（AI 判讀） | Waiting、Overprocessing | 情境假設（公開資料集，無真實成本） |
| **第二層** 流程/行政浪費 | 手動下載 SAP、Excel 彙整、人工判讀、手動寄報表 | VBA / RPA / PowerAutomate / PowerBI | Motion、Waiting、Underutilized talent | 自動化耗時可**實測** |

**敘事主從關係**：**第二層（流程自動化）是主角**，第一層（AI 模型）是它自動化處理的「判讀引擎/內容」。ASML 職缺主打第二層；第一層當技術亮點，兩層在 ROI 表**分列**，互相加分、不打架。

---

## 3. 效益計算方法（誠信原則）

每個數字必須可溯源，區分「實測」與「假設推算」：

- 🟢 **實測（硬）**：自動化單次耗時（碼錶/程式計時）、模型 Precision/Recall/F1、重建誤差比、消除的手動步驟數、開發投入工時。
- 🟡 **假設（透明）**：每天執行次數、使用人數、年工作天、人力成本/小時、第一層維護/停機成本。

**做法**：`06-lean-lss/roi-validation.xlsx` 做成「假設為明確輸入格、ROI 為其函數」的模型。綠色實測、黃色假設一目了然。面試話術：「綠色是我實測的，黃色換成 ASML 真實數字，公式立刻算出貴司效益。」——這正是 JD 的 "benefit validator" 所要的嚴謹。

**禁止**：把假設推算的金額講成實測值；捏造任何未在素材中出現的數字。

---

## 4. Repo 結構

```
predictive-maintenance-lean-ops/
├── README.md                    # 總覽 + DMAIC 故事線（中文為主）+ 兩層浪費圖
├── 01-core-model/               # 【現有】VAE 核心
│   ├── notebooks/               #   訓練 notebook、MCP notebook
│   ├── server/                  #   vae_mcp_server.py
│   └── docs/                    #   背景、MCP 說明、效益 xlsx、流程圖、小抄
├── 02-automation-vba/           # 【真做】VBA 巨集：清理模擬 SAP 匯出 → 彙整報表
│   ├── src/                     #   *.bas 巨集原始碼
│   ├── sample-data/             #   模擬 SAP 匯出 CSV（含刻意的髒資料）
│   └── README.md                #   使用說明 + 手動 vs 自動計時
├── 03-rpa-power-automate/       # 【真做】Power Automate Desktop：RPA 自動下載+寄信
│   ├── flow-export/             #   流程匯出檔（.txt/.json）
│   ├── screenshots/             #   流程截圖
│   └── README.md
├── 04-powerapps-design/         # 【設計稿】現場查詢 App 線框圖 + 畫面規格
│   ├── wireframes/              #   線框圖（SVG/PNG）
│   └── README.md                #   畫面規格、資料流、與 VAE 串接概念
├── 05-powerbi-dashboard/        # 【真做】PowerBI Desktop 儀表板
│   ├── dashboard.pbix           #   （二進位，git 追蹤）
│   ├── screenshots/             #   KPI、健康趨勢、HK 分層看板截圖
│   └── README.md
├── 06-lean-lss/                 # DMAIC 文件、價值流圖(VSM)、ROI 驗證
│   ├── DMAIC.md
│   ├── value-stream-map.md
│   └── roi-validation.xlsx
├── docs/
│   ├── interview-cheatsheet.md  # STAR 面試小抄（對應 ASML JD）
│   └── superpowers/specs/       # 本規格文件
├── .gitignore
└── requirements.txt             # 核心模型 Python 依賴
```

---

## 5. 工具真做/設計界線（個人版 Microsoft 帳號限制）

| 工具 | 狀態 | 原因 |
|------|------|------|
| VBA 巨集 | 🟢 真做 | Excel 桌面版完整支援 |
| Power BI Desktop | 🟢 真做 | 免費、本機建 .pbix，不需帳號 |
| Power Automate **Desktop**（RPA） | 🟢 真做 | Windows 11 內建免費 |
| Power Apps | 🟡 設計稿 | 個人帳號無法建 App（需公司 tenant + Dataverse）→ 線框圖 + 規格 |

---

## 6. 分階段執行計畫

| 階段 | 產出 | 類型 | 主要驗收 |
|------|------|------|---------|
| **P0** 基礎建置 | repo 骨架、搬入 VAE 核心、總 README、.gitignore、git init | 🟢 | repo 可 commit，README 講清兩層浪費故事線 |
| **P1** Lean 骨架 | `06-lean-lss/DMAIC.md`、`value-stream-map.md`、定義第二層浪費與基線工時 | 🟢 | DMAIC 五階段完整、VSM 標出浪費點 |
| **P2** VBA | 模擬 SAP 匯出 CSV + `*.bas` 巨集（清理→彙整）+ 手動/自動計時 | 🟢 | 巨集可跑、實測省時數字產生 |
| **P3** RPA | Power Automate Desktop 流程（自動抓檔+寄信）+ 匯出檔 + 截圖 + 說明 | 🟢 | 流程可重現、截圖齊全 |
| **P4** PowerApps 設計 | 現場工具線框圖 + 畫面規格 + 與 VAE 串接概念 | 🟡 | 線框圖清楚、規格可被工程師實作 |
| **P5** PowerBI | `dashboard.pbix` + KPI/健康趨勢/HK 分層看板截圖 + 說明 | 🟢 | 儀表板呈現三層 HK 看板 |
| **P6** ROI 驗證 | `roi-validation.xlsx`（實測綠/假設黃）+ 兩層效益分列 | 🟢 | 每格可溯源、ROI 為假設函數 |
| **P7** 收尾 | 面試小抄、README 補圖、推上 GitHub | 🟢 | repo 上 GitHub、小抄對齊 JD |

**依賴關係**：P0 → P1 →（P2、P3、P4、P5 可平行）→ P6（需 P2 的實測數字）→ P7。

---

## 7. 成功標準

1. GitHub 上有一個結構清晰、中文為主的整合 repo，同時展現 AI 深度與 Lean 自動化落地能力。
2. JD 六大關鍵字（Lean/LSS、VBA、PowerAutomate、PowerApps、PowerBI、ROI/benefit validation）在 repo 中都有對應實體產出或設計稿。
3. 每個效益數字可溯源，實測/假設清楚標註，面試問不倒。
4. 一份對齊 ASML JD 的 STAR 面試小抄。

## 8. 非目標（YAGNI）

- 不重訓或改進 VAE 模型本身（維持現狀當亮點）。
- 不追求 PowerApps 真實部署（個人帳號限制，設計稿即可）。
- 不接真實 SAP（用模擬匯出檔）。
- 不做 CI/CD、測試框架等與求職展示無關的工程。
