# 把專案推上 GitHub

> repo 已在本機完成所有 commit，只差建立遠端並推送。你沒裝 GitHub CLI，用網頁建立最簡單。

## 步驟

### 1. 在 GitHub 網頁建立空 repo
1. 登入 https://github.com → 右上 **+** → **New repository**
2. Repository name：`predictive-maintenance-lean-ops`
3. 說明（選填）：`VAE predictive maintenance extended into a DMAIC Lean automation pipeline (VBA / Power Automate / Power BI)`
4. 選 **Public**（求職展示用）或 Private（僅自己看）
5. **不要**勾「Add a README / .gitignore / license」（本機已有，避免衝突）
6. 按 **Create repository**

### 2. 在本機連結遠端並推送
GitHub 建好後會顯示指令，用「**…or push an existing repository**」那段。在專案資料夾執行：

```bash
cd "C:\Users\User\Desktop\predictive-maintenance-lean-ops"
git branch -M main
git remote add origin https://github.com/<你的帳號>/predictive-maintenance-lean-ops.git
git push -u origin main
```

> 把 `<你的帳號>` 換成你的 GitHub 使用者名稱。

### 3. 驗證
- 推送成功後，重新整理 GitHub 頁面，應看到所有資料夾與檔案。
- README 會自動顯示在首頁（含資料流圖與關鍵成果）。

## 常見問題
- **要求登入**：第一次 push 會跳瀏覽器要你授權 GitHub，照著登入即可（不需在終端機打密碼）。
- **remote 已存在**：若 `git remote add` 說 origin 已存在，用 `git remote set-url origin <網址>` 覆蓋。
- **推不上去/被拒**：確認 repo 是空的（沒勾 README），或先 `git pull --rebase origin main` 再 push。

## 建議：把大檔用 Git LFS（選配）
`dashboard.pbix`、`.xlsm`、`fact_readings.csv` 較大。若之後檔案變多，可考慮 Git LFS 管理二進位檔（非必要，目前直接 push 也可）。
