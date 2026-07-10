# P4 — Power Apps 設計稿：現場健康查詢 App

> **對應 ASML JD：** *"Solutions developer, to deliver applications to help CS site operation or teammates to do systematic analysis, data tracking and data visualization"* · *"PowerAPPS"*
> **消除的浪費：** Waiting（現場人員不用等主管查系統）、Motion（不用回辦公室開 Excel）

---

## 為何是「設計稿」而非可運作 App

Power Apps 需要**公司/學校 Microsoft 365 tenant**（含 Dataverse / Premium 連接器）才能建立與部署。本專案使用**個人 Microsoft 帳號**，無法實際建置。

因此本階段誠實地產出**設計稿**：線框圖 + 畫面規格 + 資料流 + 「若在 ASML tenant 如何實作」。面試時可說明：「這是我設計的現場工具，實作需要公司環境的 Dataverse 與自訂連接器。」——完全站得住腳，也展現 solutions developer 的設計能力。

---

## 三個畫面（線框圖）

| 畫面 | 檔案 | 用途 |
|------|------|------|
| 1. 機隊健康總覽 | [`wireframes/screen1-fleet-overview.svg`](wireframes/screen1-fleet-overview.svg) | 100 台一覽、KPI、依警告率排序、搜尋 |
| 2. 單台健康明細 | [`wireframes/screen2-engine-detail.svg`](wireframes/screen2-engine-detail.svg) | 狀態橫幅、健康趨勢、建議行動、建立工單 |
| 3. 即時健康查詢 | [`wireframes/screen3-whatif-check.svg`](wireframes/screen3-whatif-check.svg) | 輸入感測讀數 → 呼叫 VAE → 即時判讀 |

---

## 畫面規格

### 畫面 1 — 機隊健康總覽（首頁）

| 元件 | 內容 | 資料來源 |
|------|------|---------|
| 搜尋框 | 依 EquipmentID 篩選 | 本地過濾 |
| KPI 卡 ×3 | 總機台 100 / 有警告 86 / 急件 25 | `Summary` 彙總表 |
| 排序下拉 | 依警告率 / 依最新 cycle / 依編號 | — |
| 機台清單 | 每列：狀態燈、編號、警告率、最新 cycle、狀態標籤 | `Summary` 彙總表 |
| 狀態燈色 | 🔴 有警告且急件 / 🟡 有警告 / 🟢 健康 | 依警告率門檻 |

**Power Apps 公式示意（Gallery.Items）**：
```
SortByColumns(
    Filter(colSummary, StartsWith(EquipmentID, txtSearch.Text)),
    "WarningRate", Descending
)
```

### 畫面 2 — 單台健康明細

| 元件 | 內容 | 資料來源 |
|------|------|---------|
| 狀態橫幅 | Warning / Healthy + 模型說明 + 潛空間座標 z | 該機台最新一筆 |
| 指標卡 ×2 | 最新 Cycle、近 30 筆警告率 | `model_predictions.csv` |
| 趨勢圖 | 近 30 個 cycle 的健康分數折線 | `model_predictions.csv` |
| 建議行動 | 依狀態動態產生（檢查、備品、工單） | 規則 |
| 按鈕 | 建立工單 / 標記已檢查 | 寫回 Dataverse |

### 畫面 3 — 即時健康查詢（連接模型）

| 元件 | 內容 |
|------|------|
| 機台下拉 | 選 ENG-001 ~ ENG-100，自動帶入該機台最新讀數 |
| 關鍵感測輸入 | 現場可調整 4 個關鍵感測值（其餘用預設） |
| 執行按鈕 | 呼叫 VAE 推論 → 回傳判讀 |
| 結果卡 | Healthy / Warning、1-NN 最近樣本標籤、潛空間座標 z、建議 |

> **判讀方法（與 notebook 一致）**：VAE 把讀數壓成 2 維 embedding，找**最近的 support 樣本**，取其標籤（High-risk→Warning / Low-risk→Healthy）。這是 1-NN 投票，**沒有距離門檻**。線框圖中的距離值（0.00x 級）僅供參考，非判讀依據。

**Power Apps 公式示意（按鈕 OnSelect）**：
```
Set(gblResult,
    VAEConnector.ClassifyEngineHealth({
        sensor_readings: [ ... 21 個感測值 ... ]
    })
)
```

---

## 資料流與整合架構

```
┌────────────┐   讀取彙總    ┌─────────────────┐
│ Power Apps │◄──────────────│ Dataverse /      │  ← 巨集/RPA 寫入的每日彙總
│ (現場人員) │               │ SharePoint List  │
└─────┬──────┘               └─────────────────┘
      │ 即時查詢（畫面3）
      ▼
┌──────────────────┐   HTTP    ┌───────────────────┐
│ 自訂連接器        │──────────►│ VAE 推論 API       │  ← 由 vae_mcp_server 概念
│ (Custom Connector)│           │ (classify_health)  │     改寫成 REST 端點
└──────────────────┘           └───────────────────┘
```

---

## 若在 ASML tenant 如何實作（面試可講）

1. **資料層**：巨集/RPA 產出的每日彙總寫入 **Dataverse** 資料表（或 SharePoint List）。
2. **展示層**：Power Apps Canvas App 三畫面，Gallery 綁定 Dataverse。
3. **模型整合**：把 VAE 推論包成 **REST API**（Azure Functions / 容器），用 **Power Apps 自訂連接器**呼叫；畫面 3 的「執行判讀」即打此 API。
4. **權限**：以 Azure AD 群組控管現場人員 / 主管檢視範圍。
5. **通知**：結合 Power Automate，Warning 自動推播 Teams / Email。

---

## 誠信說明

- 本階段為**設計稿**，因個人 Microsoft 帳號無 Power Apps tenant，未實際部署。
- 線框圖中的數字（ENG-034 警告率 16.3%、最新 cycle 203、潛空間 z=(−1.00, 1.79)；ENG-031 警告率 26.5% 等）取自 [01-core-model](../01-core-model/) 的**真實模型輸出**，非虛構。
- 「VAE 推論 API」為概念整合；目前模型以 notebook / 評分腳本形式存在，尚未部署為線上端點。
