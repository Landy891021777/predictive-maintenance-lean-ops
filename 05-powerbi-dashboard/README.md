# P5 — Power BI 儀表板（Hoshin Kanri 三層看板）

> **對應 ASML JD：** *"data visualization"* · *"dashboard"* · *"HK BI (Hoshin Kanri Business Intelligence)... dashboard system design in each tier to support right decision in right time"* · *"digital measurement and monitoring"*
> **工具：** Power BI Desktop（免費，個人帳號可用，本機建置）

---

## 這一步在整條資料流的位置

```
[01] VAE 模型判讀 → [02] VBA 清理彙總 → SAP 匯出檔（lifecycle）
        ↓ prepare_powerbi_data.py（與 VBA 相同清理規則）
   data/fact_readings.csv   ← 乾淨事實表（13,096 列，Power BI 直接載入）
        ↓ ★ 本階段
   Power BI 三層看板：Tier1 高層 KPI / Tier2 部門趨勢 / Tier3 現場明細
```

**資料一致性**：`fact_readings.csv` 由 [`prepare_powerbi_data.py`](prepare_powerbi_data.py) 產生，用**與 VBA 巨集完全相同的清理規則**（去重、TRIM、統一大小寫、千分位、日期），輸出 **13,096 列、1,693 筆 Warning**——與 P2 巨集、P6 ROI 完全對得上。

---

## 資料源

| 檔案 | 內容 |
|------|------|
| `data/fact_readings.csv` | 乾淨事實表：ExportDate、EquipmentID、Cycle、12 感測器、LatentZ1/Z2、NearestDistance、PredictedStatus、IsWarning、WorkOrder、MaintenanceCost |

重新產生：`py -3 prepare_powerbi_data.py`

---

## Hoshin Kanri 三層看板設計

> HK 精神：**右時間給右決策**——不同層級的人看不同顆粒度。

```
┌─────────────────────────────────────────────────────────┐
│ TIER 1 · 高層 KPI（一眼看全局）                           │
│  [機台數 100] [警告總數 1,693] [警告率] [有警告機台] [總維護成本] │
├─────────────────────────────────────────────────────────┤
│ TIER 2 · 部門趨勢與分析                                    │
│  [警告趨勢折線圖]   [Top10 高警告機台]   [潛空間散佈圖 z1×z2]   │
├─────────────────────────────────────────────────────────┤
│ TIER 3 · 現場機台明細                                      │
│  [每台明細表：讀數/警告數/警告率/維護成本，條件式色階]           │
├─────────────────────────────────────────────────────────┤
│ 篩選器：ExportDate（匯出日）· PredictedStatus（狀態）          │
└─────────────────────────────────────────────────────────┘
```

---

## DAX 量值（先全部建好，再拉視覺）

在 Power BI「**模型化 → 新增量值**」逐一貼上：

```DAX
Total Readings = COUNTROWS ( fact_readings )
```
```DAX
Total Warnings = SUM ( fact_readings[IsWarning] )
```
```DAX
Warning Rate = DIVIDE ( [Total Warnings], [Total Readings] )
```
```DAX
Engine Count = DISTINCTCOUNT ( fact_readings[EquipmentID] )
```
```DAX
Warning Engines =
CALCULATE (
    DISTINCTCOUNT ( fact_readings[EquipmentID] ),
    fact_readings[IsWarning] = 1
)
```
```DAX
Total Maintenance Cost = SUM ( fact_readings[MaintenanceCost] )
```
```DAX
Avg Nearest Distance = AVERAGE ( fact_readings[NearestDistance] )
```
```DAX
-- 來自 P6 ROI 的自動化年省工時（靜態，說明用）
Annual Hours Saved = 539
```

---

## 逐視覺建置（Tier by Tier）

### TIER 1 — 高層 KPI（頁面上方一排「卡片」視覺）

| 視覺 | 類型 | 欄位/量值 | 預期值 |
|------|------|-----------|--------|
| 機台數 | 卡片 (Card) | `Engine Count` | 100 |
| 警告總數 | 卡片 | `Total Warnings` | 1,693 |
| 警告率 | 卡片 | `Warning Rate`（格式化為百分比） | 12.9% |
| 有警告機台 | 卡片 | `Warning Engines` | 86 |
| 總維護成本 | 卡片 | `Total Maintenance Cost`（千分位） | 依資料 |

> 做法：插入「卡片」視覺 → 把對應量值拖到「欄位」。5 張排成一列。

### TIER 2 — 部門趨勢與分析

**① 警告趨勢（折線圖 Line chart）**
- X 軸：`ExportDate`
- Y 軸：`Total Warnings`
- 預期：156 → 286 → 1,251 明顯上升（真實退化趨勢）

**② Top 10 高警告機台（橫條圖 Clustered bar chart）**
- Y 軸：`EquipmentID`
- X 軸：`Total Warnings`
- 篩選：視覺層級篩選 → `Total Warnings` 的 Top N = 10
- 預期：ENG-031、ENG-034、ENG-020… 排前面

**③ 潛空間散佈圖（散佈圖 Scatter chart）— 展示 VAE embedding**
- X 軸：`LatentZ1`（設為「不摘要」/ Don't summarize）
- Y 軸：`LatentZ2`（不摘要）
- 圖例：`PredictedStatus`（Healthy 綠 / Warning 紅）
- 詳細資料：`EquipmentID`
- 預期：健康與警告在潛空間分成兩區——**視覺化你的模型如何分辨健康狀態**

### TIER 3 — 現場機台明細（表格 Table / 矩陣 Matrix）

- 資料表視覺，欄位：
  - `EquipmentID`
  - `Total Readings`
  - `Total Warnings`
  - `Warning Rate`
  - `Total Maintenance Cost`
- **條件式格式設定**：對 `Warning Rate` 欄 → 資料橫條或色階（紅高綠低），一眼看出高風險機台

### 篩選器（Slicer）
- 插入兩個「交叉分析篩選器」：`ExportDate`、`PredictedStatus`
- 讓看板可互動：點某一天 / 只看 Warning

---

## 逐步操作教學（Power BI Desktop）

1. 開始搜尋 **Power BI Desktop**（沒有就 Microsoft Store 免費安裝）
2. **取得資料 → 文字/CSV** → 選 `05-powerbi-dashboard\data\fact_readings.csv` → **載入**
3. 檢查資料型別：`ExportDate` 應為日期、`IsWarning`/`MaintenanceCost`/`LatentZ1/2` 應為數值（不對就在 Power Query 改）
4. **模型化 → 新增量值**，把上面 8 個 DAX 量值逐一建好
5. 依「三層看板設計」擺版面：上排卡片、中排三張圖、下排明細表
6. 加兩個篩選器
7. **檔案 → 儲存** 成 `05-powerbi-dashboard\dashboard.pbix`
8. 依下方清單截圖

### 📸 截圖清單（放 screenshots/）
- [ ] 完整儀表板全貌（三層）
- [ ] Tier1 KPI 卡片列（100 / 1,693 / 12.9% / 86）
- [ ] 警告趨勢折線圖（156→286→1,251）
- [ ] 潛空間散佈圖（健康/警告分兩區）
- [ ] Tier3 明細表（含色階）

---

## 誠信說明

- 所有數字源自 `fact_readings.csv`，與 P2 巨集、P6 ROI 完全一致（13,096 列、1,693 警告）。
- `PredictedStatus` 為真實 VAE 模型判讀；`MaintenanceCost` 為模擬欄位（見 [02-automation-vba](../02-automation-vba/) 說明）。
- Power BI Desktop 本機建置，不需付費帳號；發佈到 Power BI Service 才需公司帳號（本專案止於本機 .pbix + 截圖）。
- 預設用 **lifecycle** 資料（退化趨勢）。若要做 **snapshot**（今日艦隊快照）版，改指向 `snapshot` 資料夾重跑 prepare 腳本即可。
