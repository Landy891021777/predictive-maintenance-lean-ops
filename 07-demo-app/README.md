# 07 — 互動展示網站

> 把 01~06 的成果變成一個可以**自己動手驗證**的網站。

**線上版：** https://landy-predictive-maintenance.streamlit.app/

**本機執行：**

```bash
pip install -r requirements.txt
streamlit run 07-demo-app/app.py
```

---

## 這裡有什麼

| 分頁 | 你可以做什麼 | 對應履歷主張 |
|---|---|---|
| 總覽 | 一頁看懂兩層浪費、資料流、關鍵數字 | 整條 bullet |
| 即時判讀 | 拉 21 顆感測器滑桿當場判讀；**導入新引擎**（上傳 CSV 或示範 FD003/FD002 機隊），附適用範圍檢查 | `VAE-based fault-detection framework` |
| 機隊軌跡 | 13,096 筆逐筆判讀、單台退化軌跡、被漏判的 2 台 | 早期異常偵測 |
| 自動化 | 髒匯出檔 → 一鍵清理彙總 → 下載報表；與 Power Automate 實際產出逐項對照 | `Automated reporting via RPA/Power Automate` |
| AI 助理 | 用自然語言問維修手冊、SOP、工單、交接紀錄，回答逐句標出處 | `AI chatbot ... powered by RAG and an LLM API` |
| 效益驗證 | 拉假設滑桿即時重算 ROI；84% / 36% 的 value-driver 推導與基準敏感度；品質效益 | `reduced maintenance costs by 84% and equipment downtime by 36%` |

---

## 為什麼線上不裝 PyTorch

Streamlit Community Cloud 免費層記憶體約 1GB，而 `pip install torch` 預設會抓 CUDA 版
wheel（2GB+），部署很容易失敗或 OOM。

這個 VAE 的 encoder 本質上只是三個矩陣運算：

```
h  = ReLU(x @ W1ᵀ + b1)
mu = h @ Wmuᵀ + bmu
```

所以 `build/export_artifacts.py` 在本機把 `vae_model.pth` 的權重匯出成 `.npz`，
線上只用 NumPy 重算。**模型是真的在跑，只是換了一個執行引擎。**

---

## 資產（assets/，約 480 KB，隨 repo 一起部署）

| 檔案 | 內容 |
|---|---|
| `vae_weights.npz` | VAE 全部權重（encoder + decoder） |
| `scaler.npz` | MinMaxScaler 的 `scale_` / `min_`，完全重現 sklearn 的 transform |
| `support.npz` | support set 的 14,441 個 embedding 與標籤（1-NN 用） |
| `test_readings.npz` | test_FD001 的 13,096 筆讀數（21 感測器，**float64**） |
| `meta.json` | 門檻、感測器統計、驗證指標 |

> `test_readings.npz` 必須存 float64。部分感測器數值大但全距極窄（s_13 約 2388、全距 0.49），
> 存成 float32 會讓縮放後的捨入誤差放大到 2.4e-4，足以讓 1-NN 在邊界改判 —— 實測會造成
> 13,096 筆中有 61 筆與 `model_predictions.csv` 不一致。

---

## 重新產生資產與驗證

```bash
pip install -r requirements-dev.txt          # 需要 torch
py -3 07-demo-app/build/export_artifacts.py  # 匯出 assets/
py -3 07-demo-app/build/verify_numpy_path.py # 驗證模型推論與既有結果一致
py -3 07-demo-app/build/verify_cleaning.py   # 驗證清理邏輯與 RPA 實際產出一致
```

`verify_numpy_path.py` 是回歸測試，任何改動後都該跑。它檢查兩件事：

- **[A]** 對 100 台引擎最後一個 cycle 的判讀，必須重現 `model_validation.md` 的
  Accuracy 0.8500 與混淆矩陣 `[[54,13],[2,31]]`
- **[B]** 對全部 13,096 筆的判讀與潛空間座標，必須與 `model_predictions.csv` 逐筆一致

> 「最近距離」刻意不設嚴格門檻：support embedding 由 NumPy 重算，與原本 PyTorch 版每個
> 座標差約 7e-7；健康樣本在潛空間極密集，這點擾動會讓「最近的是哪一個點」換人，
> 但換到的點標籤相同，判讀不受影響。

---

## 誠信原則

- 🟢 **實測** — 在真實資料上實際跑出來的（模型指標、自動化耗時、消除的錯誤筆數）
- 🟡 **情境假設** — 推估值，輸入可調、公式公開（維護成本 −84%、停機 −36%、ROI）

公開資料集沒有真實成本資料，因此成本面效益一律標為情境假設，不講成實測。
本案的 SAP 匯出檔為**模擬**檔（格式仿 SAP 匯出的髒檔），**未串接真實 SAP 系統**。

---

## 自動化頁為什麼跑的是 Python

雲端沒有 Windows 與 Excel，VBA 巨集與 Power Automate Desktop 都無法執行。
`core/cleaning.py` 把 `02-automation-vba/src/CleanAndSummarize.bas` 的規則逐條重現，
`build/verify_cleaning.py` 拿 Power Automate **實際跑出的報表**
（`03-rpa-power-automate/outbox/DailyHealthReport_20260711.xlsm`）當對照組：

- run log 8 項（原始列 13,750、去重 654、乾淨列 13,096、大小寫修正 2,001、Warning 1,693、缺距離 386、缺成本 901）全數一致
- 100 台機台彙總的讀數與警告數零差異，成本合計最大誤差 4.7e-10

重現時必須照抄的 VBA 細節：`Val()` 只解析開頭數字；`status_fixed` 比的是**去空白後**的原值；
欄位數不是 22 的列靜默丟棄但仍計入原始列；缺值與大小寫修正只統計保留下來的列。

> **耗時有兩次實測**：Alt+F8 互動執行 1.6 秒（562×），經 Power Automate 無人值守執行 1.844 秒（488×）。
> 兩者皆為真實量測，ROI 使用前者。網頁上 Python 重現的耗時不計入效益。

---

## AI 助理（RAG）

### 文件庫（`build/build_corpus.py`，100 段、6 份文件）

| 性質 | 文件 | 說明 |
|---|---|---|
| 🟡 模擬 | 維修手冊、異常處置 SOP、維修工單（61 張）、交接班紀錄 | CMAPSS 沒有這類文件；但其中的引擎編號、cycle、判讀結果、感測器範圍與退化方向**全部由真實資料計算**，且刻意不含真實剩餘壽命 |
| 🟢 真實 | 模型卡、精實改善與效益 | 以最終數字重新整理。`06-lean-lss/DMAIC.md` 與 `value-stream-map.md` 為 P1 草稿，含過期假設，不直接收錄 |

### 檢索：評估後選擇「語意向量 + 機台代號比對」（`build/rag_eval.py`，36 題）

| 方式 | Hit@1 | Hit@3 | MRR |
|---|---|---|---|
| BM25 | 63.9% | 88.9% | 0.776 |
| 語意向量（gemini-embedding-2） | 94.4% | 97.2% | 0.961 |
| 混合（BM25 + 向量，RRF） | 77.8% | 94.4% | 0.871 |
| **語意向量 + 代號比對（線上使用）** | **97.2%** | **97.2%** | **0.979** |

原本預期混合檢索最好，實測不是：BM25 在這份語料雜訊多，合併後反而拉低排序。
但純向量會混淆相似代號（問 ENG-006 時把 ENG-056 排第一），因此加上規則：問題含 ENG-xxx 時，含該代號的段落優先。

> 限制：機台代號 12 題是發現上述混淆後才加入，對最終方法不算獨立驗證；題庫僅 36 題。

### 生成與防護

- Gemini 免費層，以標準庫 `urllib` 呼叫 REST API（不裝 SDK）。模型依序 `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.5-flash` → `gemini-3.6-flash`；404、429、5xx、逾時或連線中斷都換下一個，忙碌／逾時的模型 2 秒後再試一輪，整題上限 50 秒（免費額度按模型分開計算）
- 主模型選 `3.5-flash-lite`：實測回應 1–2 秒且遵守 prompt 規則；`3.6-flash` 免費層每日僅 20 次，不適合當公開網站主模型
- 生成失敗退回原文段落時**不扣**使用者的提問次數
- System prompt：僅依段落回答、逐句標出處、數字照抄、模擬文件須告知、**但書必須保留**、防 prompt injection、離題婉拒、只在問真實維修決策時加免責
- **出處驗證**：回答引用的片段編號必須在檢索結果中，否則標紅
- **降級**：embedding 失敗 → BM25；生成全部失敗 → 直接列出原文段落
- **防濫用**：每次瀏覽 15 題、每題 200 字；6 個建議問題使用預先產生的回答（`build/build_faq.py`），面試當天額度用完仍可展示

### 紅隊測試（`build/rag_redteam.py`，7 題，人工複核全數通過）

文件外的事實、不存在的引擎（ENG-150）、prompt injection、離題（寫程式）、真實飛安決策、數字陷阱（36% 的精確值）、誘導捏造維修結果。

### 金鑰

本機：`.streamlit/secrets.toml`（已列入 `.gitignore`，範本見 `secrets.toml.example`）。
雲端：Streamlit Cloud 後台 **Settings → Secrets** 貼上 `GEMINI_API_KEY = "..."`。
未設定金鑰時，網站自動以「僅檢索」模式運作，建議問題仍顯示預先產生的回答。

### 重建順序

```bash
py -3 07-demo-app/build/build_corpus.py   # 文件庫
py -3 07-demo-app/build/embed_corpus.py   # 段落向量（需金鑰；免費層 embedding 每分鐘 100 次）
py -3 07-demo-app/build/rag_eval.py       # 檢索評估
py -3 07-demo-app/build/build_faq.py      # 建議問題的預存回答
py -3 07-demo-app/build/rag_redteam.py    # 紅隊測試
```

---

## 導入新引擎與適用範圍檢查

使用者問「導入新引擎也能判讀嗎？」—— 用同系列、附真實答案的 NASA FD002–FD004 實測
（`build/export_new_engine_assets.py`，評估方式比照 FD001：每台最後一個 cycle）：

| 資料集 | 差異 | Accuracy | 快故障抓到 | 未加檢查：誤判為健康 | 加了檢查：誤判為健康 |
|---|---|---|---|---|---|
| FD001 | 訓練工況 | 85.0% | 31/33 | 2/33 | 2/33 |
| FD003 | 同工況，多一種失效模式 | 72.0% | 14/36 | 22/36 | **5/36** |
| FD002 | 六種運轉條件 | 71.4% | 14/86 | 72/86 | **2/86** |
| FD004 | 六種運轉條件、兩種失效模式 | 69.0% | 6/82 | 76/82 | **0/82** |

- **Accuracy 約 70% 是假象**：快故障只佔約三分之一，全部判 Healthy 也有約 67%
- **適用範圍檢查**：讀數到最近訓練點的距離 > 0.0209（FD001 測試集第 99 百分位）即超出範圍。
  FD002 六種運轉條件中，只有與訓練資料相同的海平面條件落在範圍內
- **超出範圍時**：判 Warning 照樣顯示（17/17 真的快故障）；判 Healthy 改為「無法確認」（495 台中 163 台其實快故障）

> 限制：距離門檻事先訂定，但「Warning 可信、Healthy 不可信」是看過四組資料後歸納的事後觀察，Warning 側僅 17 台。

示範機隊以固定亂數種子分層抽樣（每組 4 台快故障、4 台健康），不挑選對模型有利的引擎。
上傳檔接受 NASA 原始格式（26 欄無表頭）或含 `s_1…s_21` 的 CSV；格式錯誤會回傳可讀的說明。

```bash
py -3 07-demo-app/build/export_new_engine_assets.py   # 評估 + 示範機隊（需本機 NASA 原始資料）
py -3 07-demo-app/build/verify_new_engine.py          # 回歸測試（上傳格式、錯誤處理、「超出範圍永不回報 Healthy」）
```

---

## 效益驗證頁

- **預設值直接讀自 `06-lean-lss/roi-validation.xlsx`**，公式與試算表相同（`core/roi.py`）；試算表改了網頁自動跟著變
- 流程自動化 ROI：🟢 手動 900 秒、自動 1.6 秒（可切換為 Power Automate 那次的 1.844 秒）；🟡 次數、人數、工作天、時薪、導入工時可調，附敏感度圖
- 設備健康 84% / 36%：value-driver 公式攤開，基準可調，可切換取整（96% / 81%）與未取整（96.43% / 80.60%）
- `build/verify_roi.py`：重現校準版（119.8 小時、ROI 199.5%、回本 80.1 工作天）與早期樂觀假設（539 小時、ROI 1,248%），並核對 84.0% / 36.7% / 85.7% / 35.3%
