# 🚀 IEEPA Refund Calculator 部署指南 (整合式映像檔)

本文件說明如何使用 `Dockerfile.allinone` 編譯整合式映像檔 (包含 Nginx, Frontend, Backend, Redis)，並部署至遠端伺服器。

---

## 1. 開發機 (Local Machine) 流程

在您的開發端完成映像檔的編譯與上傳。

### 步驟 1: 編譯整合式映像檔
請確保在專案根目錄 (`C:\project\ieepa-refund-calculator`) 執行：
```powershell
# 使用 Dockerfile.allinone 編譯並標記版本
docker build -f "Dockerfile.allinone" --force-rm -t 10.161.254.241/dimerco/ieepa-refund-calculator:V1.0.0 .
```

### 步驟 2: 登入遠端 Docker Registry
```powershell
docker login 10.161.254.241
```

### 步驟 3: 推送映像檔 (Push)
```powershell
docker push 10.161.254.241/dimerco/ieepa-refund-calculator:V1.0.0
```

---

## 2. 目標虛擬機 (Target VM) 部署流程

登入目標 VM 後，請依照環境選擇對應的部署方式。

### 步驟 4: 拉取最新映像檔
```bash
docker pull 10.161.254.241/dimerco/ieepa-refund-calculator:V1.0.0
```

### 步驟 5: 執行容器

#### A. Staging (開發/測試環境)
此環境通常開放 `8080` 與 `8443` 埠供內部測試使用。
> **注意**: 請確保當前目錄下有 `certs` 資料夾 (含 `server.crt` 與 `server.key`)。

```powershell
docker run -d `
  --name IEEPA-Calculator-Service `
  -p 8080:80 -p 8443:443 `
  -e ENVIRONMENT=development `
  -v "ieepaDataVolume:/data" `
  -v "${PWD}\certs:/etc/nginx/ssl:ro" `
  10.161.254.241/dimerco/ieepa-refund-calculator:V1.0.0
```

#### B. Production (正式環境)
此環境對應 Dimerco 正式環境路徑與埠號 (`39080`, `39443`)。

```bash
docker run -d \
  --name IEEPA-Calculator-Service \
  -p 39080:80 -p 39443:443 \
  -e ENVIRONMENT=production \
  -v "ieepaDataVolume:/data" \
  -v "/home/docker/ca/2025-2026/cert.crt:/etc/nginx/ssl/server.crt:ro" \
  -v "/home/docker/ca/2025-2026/key.key:/etc/nginx/ssl/server.key:ro" \
  10.161.254.241/dimerco/ieepa-refund-calculator:V1.0.0
```

---

## 3. 部署注意事項

1. **憑證掛載**: 
   - 映像檔內部的 Nginx 預期憑證路徑為 `/etc/nginx/ssl/server.crt` 與 `/etc/nginx/ssl/server.key`。
   - 掛載時請確保宿主機的路徑正確。
2. **資料持久化**: 
   - 使用 `ieepaDataVolume` 或具名磁碟卷掛載至 `/data`，以確保 SQLite 資料庫與上傳的檔案不會因容器重啟而遺失。
3. **檢查狀態**:
   - 查看日誌: `docker logs -f IEEPA-Calculator-Service`
   - 進入容器檢查: `docker exec -it IEEPA-Calculator-Service sh`

---

## 4. 常見問題與排查 (Troubleshooting)

### Q1: 容器顯示 `Created` 但無法啟動，或埠號被佔用？
如果您的機器上已有其他服務佔用 80 或 443 埠 (例如 IIS 或其他 Nginx)，請調整埠號對應：
```powershell
# 將主機的 8080 對應到容器 80，8443 對應到容器 443
docker run -d -p 8080:80 -p 8443:443 ... (其餘參數不變)
```

### Q2: 修改了前端程式碼，但部署後沒看到更新？
Docker 會快取映像檔層。如果您修改了前端 `src/` 內容，執行 `docker compose up` 時請務必加上 `--build` 參數：
```powershell
docker compose up --build
```
這會強制重新執行 `Dockerfile.allinone` 中的 `npm run build` 階段。

### Q3: 沒有 Google Cloud 憑證，OCR 還能跑嗎？
可以。系統設計有自動備援機制：
1. **第一優先**: Google Document AI (需配置 `.env` 中的 Project ID 與掛載 JSON 密鑰)。
2. **備援方案**: 如果第一步失敗或未配置，系統會自動切換至容器內建的 **Tesseract OCR**。
> 注意：Tesseract 對掃描品質要求較高，若辨識率低於 50% 系統會標記為失敗。

---
*最後更新日期: 2026-03-26*
