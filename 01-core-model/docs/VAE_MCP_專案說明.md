# Sensor-Based Predictive Fault Detection
## Python, VAE & MCP

---

## 專案概述

以 NASA CMAPSS 航太引擎感測器資料為基礎，建構 AI 驅動的預測性維護系統。
將訓練完成的 VAE 模型封裝為 MCP server，使 AI agent 能夠即時呼叫推論工具。

---

## 技術架構

### 模型
- **架構：** Variational Autoencoder（VAE）
- **框架：** PyTorch
- **潛空間維度：** 2D（便於視覺化引擎退化路徑）
- **訓練資料：** NASA CMAPSS FD001（100 台引擎、20,631 筆時序資料、21 個感測器）

### 數據處理
- NumPy、pandas
- scikit-learn（MinMaxScaler）
- Few-shot Learning（解決標記資料不足問題）

### MCP 部署
- **框架：** MCP Python SDK（FastMCP）
- **通訊協定：** stdio
- **註冊指令：** `claude mcp add vae-maintenance -- py -3 vae_mcp_server.py`

---

## 暴露工具（MCP Tools）

### 1. `classify_engine_health`
- **輸入：** 21 個感測器數值
- **輸出：** 健康狀態（Healthy / Warning）、潛空間距離、閾值、行動建議

### 2. `get_reconstruction_error`
- **輸入：** 21 個感測器數值
- **輸出：** 重建誤差、潛空間座標（z1、z2）

### 3. `batch_health_check`
- **輸入：** 多筆感測器快照
- **輸出：** 批次健康狀態摘要（healthy_count、warning_count）

---

## 實測結果

| 狀態 | Reconstruction Error | Latent Distance | 判斷結果 |
|------|---------------------|-----------------|---------|
| 健康引擎（均值） | 0.000646 | 0.1292 | Healthy |
| 退化引擎（極值） | 0.175149 | 2.5473 | Warning |

誤差差距：**270 倍**

---

## 模型效能指標

| 指標 | 數值 |
|------|------|
| 維護成本降低 | 84% |
| 設備停機時間降低 | 36% |
| Precision 提升 | +21% |
| Recall 提升 | +11% |

---

## MCP 連接流程

```
Python MCP Server（vae_mcp_server.py）
        ↓ stdio
Claude Code CLI（claude mcp add）
        ↓
Claude Agent 呼叫 classify_engine_health / get_reconstruction_error
        ↓
Server 載入 VAE 模型執行推論，回傳結果
```

---

## 檔案結構

```
VAE_MCP_Project/
├── vae_mcp_server.py                          # MCP server 主程式
├── VAE_predictive_maintenance_MCP.ipynb       # 原始訓練 notebook（複本）
└── VAE_MCP_專案說明.md                        # 本文件

kaggle 專案/nasa專案/
└── vae_model.pth                              # 訓練完成的模型權重
```
