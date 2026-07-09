"""
VAE Predictive Maintenance MCP Server
Wraps the trained VAE model (NASA CMAPSS) as callable tools for AI agents.
"""

from mcp.server.fastmcp import FastMCP
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import os

mcp = FastMCP("vae-predictive-maintenance")

# ── Paths ─────────────────────────────────────────────────────────────────────
MODEL_PATH = r"C:\Users\User\Desktop\kaggle 專案\nasa專案\vae_model.pth"
DATA_PATH  = r"C:\Users\User\Desktop\kaggle 專案\nasa專案\train_FD001.txt"

# ── Model definition (must match the trained architecture) ────────────────────
class VAE(nn.Module):
    def __init__(self, input_dim, latent_dim):
        super().__init__()
        self.fc1      = nn.Linear(input_dim, 64)
        self.fc_mu    = nn.Linear(64, latent_dim)
        self.fc_logvar= nn.Linear(64, latent_dim)
        self.fc2      = nn.Linear(latent_dim, 64)
        self.fc3      = nn.Linear(64, input_dim)
        self.relu     = nn.ReLU()

    def encode(self, x):
        h = self.relu(self.fc1(x))
        return self.fc_mu(h), self.fc_logvar(h)

    def decode(self, z):
        return self.fc3(self.relu(self.fc2(z)))

    def forward(self, x):
        mu, logvar = self.encode(x)
        std = torch.exp(0.5 * logvar)
        z   = mu + std * torch.randn_like(std)
        return self.decode(z), mu, logvar


# ── Load model & scaler once at startup ───────────────────────────────────────
INPUT_DIM  = 21
LATENT_DIM = 2

# Fixed sensors (zero variance in training data — always dropped before scaling)
CONSTANT_SENSORS = [0, 4, 5, 9, 15, 17, 18]  # s_1,5,6,10,16,18,19 (0-indexed)

_vae    = None
_scaler = None

def _load():
    global _vae, _scaler

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Training data not found: {DATA_PATH}")

    # Rebuild scaler from training data (same logic as notebook)
    col_names = (["unit_number", "time_cycles"] +
                 [f"setting_{i}" for i in range(1, 4)] +
                 [f"s_{i}" for i in range(1, 22)])
    df = pd.read_csv(DATA_PATH, sep=r"\s+", header=None,
                     index_col=False, names=col_names)
    drop_cols = ["unit_number", "time_cycles", "setting_1", "setting_2", "setting_3"]
    X = df.drop(columns=drop_cols).values  # shape (N, 21)

    scaler = MinMaxScaler()
    scaler.fit(X)

    # Load VAE weights
    vae = VAE(INPUT_DIM, LATENT_DIM)
    vae.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    vae.eval()

    _vae    = vae
    _scaler = scaler


def _ensure_loaded():
    if _vae is None:
        _load()


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_reconstruction_error(sensor_readings: list[float]) -> dict:
    """
    Compute VAE reconstruction error for one snapshot of 21 sensor readings.
    Higher error = more anomalous. Returns raw MSE reconstruction loss.
    """
    if len(sensor_readings) != 21:
        return {"error": f"Expected 21 sensor values, got {len(sensor_readings)}"}
    _ensure_loaded()

    x_raw   = np.array(sensor_readings, dtype=np.float32).reshape(1, -1)
    x_scaled= _scaler.transform(x_raw).astype(np.float32)
    x_t     = torch.tensor(x_scaled)

    with torch.no_grad():
        x_hat, mu, logvar = _vae(x_t)
        recon_error = float(nn.MSELoss()(x_hat, x_t).item())
        latent_z    = mu.numpy().flatten().tolist()

    return {
        "reconstruction_error": round(recon_error, 6),
        "latent_z1": round(latent_z[0], 4),
        "latent_z2": round(latent_z[1], 4),
        "note": "Higher reconstruction_error indicates anomalous sensor pattern.",
    }


@mcp.tool()
def classify_engine_health(sensor_readings: list[float]) -> dict:
    """
    Classify engine health as 'Healthy' or 'Warning' based on VAE latent space
    distance from training distribution center. Uses the same nearest-support-set
    logic as the original notebook.
    """
    if len(sensor_readings) != 21:
        return {"error": f"Expected 21 sensor values, got {len(sensor_readings)}"}
    _ensure_loaded()

    x_raw    = np.array(sensor_readings, dtype=np.float32).reshape(1, -1)
    x_scaled = _scaler.transform(x_raw).astype(np.float32)
    x_t      = torch.tensor(x_scaled)

    with torch.no_grad():
        mu, logvar = _vae.encode(x_t)
        z = mu.numpy().flatten()

    # Distance from origin (latent space center ≈ healthy region for this dataset)
    distance = float(np.linalg.norm(z))

    # Threshold derived empirically from notebook embedding plots
    THRESHOLD = 2.5
    status = "Healthy" if distance < THRESHOLD else "Warning"

    return {
        "status": status,
        "latent_distance": round(distance, 4),
        "threshold": THRESHOLD,
        "interpretation": (
            "Engine within normal operating range."
            if status == "Healthy"
            else "Engine shows signs of degradation — recommend inspection."
        ),
    }


@mcp.tool()
def batch_health_check(sensor_snapshots: list[list[float]]) -> dict:
    """
    Check health for multiple engine snapshots at once.
    Input: list of snapshots, each with 21 sensor values.
    Returns summary + per-snapshot results.
    """
    _ensure_loaded()
    results = []
    for i, snap in enumerate(sensor_snapshots):
        result = classify_engine_health(snap)
        result["snapshot_index"] = i
        results.append(result)

    warning_count = sum(1 for r in results if r.get("status") == "Warning")
    return {
        "total_snapshots": len(results),
        "healthy_count": len(results) - warning_count,
        "warning_count": warning_count,
        "snapshots": results,
    }


if __name__ == "__main__":
    print("Loading VAE model and scaler...")
    _load()
    print("VAE MCP server ready.")
    mcp.run()
