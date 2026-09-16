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
| 即時判讀 | 拉 21 顆感測器滑桿，當場看模型判 Healthy / Warning | `VAE-based fault-detection framework` |
| 機隊軌跡 | 13,096 筆逐筆判讀、單台退化軌跡、被漏判的 2 台 | 早期異常偵測 |
| 自動化 | 髒匯出檔 → 清理 → 彙總 → 下載報表（P2） | `Automated reporting via RPA/Power Automate` |
| AI 助理 | 用自然語言問維修手冊與工單（P3） | `AI chatbot ... powered by RAG and an LLM API` |
| 效益驗證 | 拉假設滑桿，看 84% / 36% / ROI 即時重算（P4） | 效益數字 |

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
py -3 07-demo-app/build/verify_numpy_path.py # 驗證與既有結果一致
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
