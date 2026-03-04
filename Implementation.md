# 本機測試安裝指南 — IEEPA Tariff Refund Calculator

> **對象：** 一般使用者（不需要具備程式開發背景）  
> **目標：** 在你自己的電腦上把系統跑起來，並完成一次完整的測試流程  
> **預計時間：** 首次設定約 30–45 分鐘

---

## 目錄

1. [事前準備：安裝必要工具](#1-事前準備安裝必要工具)
2. [下載程式碼](#2-下載程式碼)
3. [設定環境參數（.env）](#3-設定環境參數env)
4. [產生加密金鑰](#4-產生加密金鑰)
5. [啟動所有服務](#5-啟動所有服務)
6. [建立資料庫結構](#6-建立資料庫結構)
7. [確認服務是否正常運作](#7-確認服務是否正常運作)
8. [執行第一次測試上傳](#8-執行第一次測試上傳)
9. [停止服務](#9-停止服務)
10. [常見問題排解](#10-常見問題排解)

---

## 1. 事前準備：安裝必要工具

> 這個系統使用 **Docker** 來管理所有服務，你不需要自己安裝 Python 或資料庫。只需要安裝 Docker 一個工具即可。

### 1.1 安裝 Docker Desktop

1. 前往官方網站下載：**https://www.docker.com/products/docker-desktop/**
2. 根據你的作業系統選擇版本：
   - Windows：點選 **"Download for Windows"**
   - macOS（Intel）：點選 **"Download for Mac - Intel Chip"**
   - macOS（M1/M2/M3）：點選 **"Download for Mac - Apple Silicon"**
3. 下載完成後，執行安裝程式，一路點選 **Next / Continue** 即可
4. 安裝完成後，**重新啟動電腦**
5. 重開機後，桌面右下角（Windows）或頂部選單列（Mac）應出現 Docker 的鯨魚圖示 🐳
6. 點選鯨魚圖示，確認顯示 **"Docker Desktop is running"**

> ✅ **如何確認安裝成功？**  
> 開啟「命令提示字元」（Windows）或「Terminal」（Mac），輸入以下指令並按 Enter：
> ```
> docker --version
> ```
> 應看到類似 `Docker version 25.x.x` 的輸出

### 1.2 安裝 Git（用來下載程式碼）

1. 前往：**https://git-scm.com/downloads**
2. 下載對應作業系統的版本並安裝（一路 Next 即可）
3. 安裝完成後，開啟命令提示字元 / Terminal，輸入：
   ```
   git --version
   ```
   應看到類似 `git version 2.x.x` 的輸出

### 1.3 安裝 Python（僅用於產生加密金鑰，只需一次）

1. 前往：**https://www.python.org/downloads/**
2. 點選 **"Download Python 3.11.x"**（或更高版本）
3. **⚠️ 安裝時務必勾選 "Add Python to PATH"**（這個選項在安裝畫面最下方）
4. 點選 **Install Now**
5. 完成後，在命令提示字元輸入：
   ```
   python --version
   ```
   應看到 `Python 3.11.x`

---

## 2. 下載程式碼

### 2.1 開啟命令視窗

- **Windows**：按下 `Win + R`，輸入 `cmd`，按 Enter
- **Mac**：按下 `Command + Space`，輸入 `Terminal`，按 Enter

### 2.2 選擇要放置程式碼的位置

建議放在桌面或文件資料夾，以下以桌面為例：

**Windows：**
```cmd
cd %USERPROFILE%\Desktop
```

**Mac：**
```bash
cd ~/Desktop
```

### 2.3 下載程式碼

複製貼上以下指令並按 Enter：

```bash
git clone https://github.com/Steven-Chen2021/ieepa-refund-calculator.git
```

下載完成後，進入程式資料夾：

```bash
cd ieepa-refund-calculator
```

> ✅ 你應該可以看到資料夾內有 `backend/`、`frontend/`、`docker-compose.yml` 等資料

---

## 3. 設定環境參數（.env）

> **什麼是 .env？** 這是一個設定檔，存放密碼、API 金鑰等敏感資訊。每個人的設定可能不同，所以這個檔案不會直接提供，需要你根據範本建立。

### 3.1 複製範本

**Windows（命令提示字元）：**
```cmd
copy backend\.env.example backend\.env
```

**Mac / Linux（Terminal）：**
```bash
cp backend/.env.example backend/.env
```

### 3.2 編輯 .env 檔案

用記事本（Windows）或文字編輯器（Mac）開啟 `backend/.env`：

**Windows：**
```cmd
notepad backend\.env
```

**Mac：**
```bash
open -e backend/.env
```

### 3.3 填入必要參數

請根據以下說明，逐項修改 `backend/.env` 中標有 `REPLACE_WITH_` 的欄位：

---

#### 🔑 SECRET_KEY — 應用程式加密金鑰

**說明：** 這是用來保護 session 資料的隨機字串，每台電腦應各自生成不同的值。

**生成方式：** 在命令視窗執行：
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
你會看到一串像這樣的輸出（每次執行都不同）：
```
a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1
```

把這串值複製，替換 `.env` 中的 `REPLACE_WITH_32_BYTE_RANDOM_HEX`

---

#### 🔑 JWT_SECRET_KEY — JWT 登入憑證金鑰

**說明：** 用來保護使用者登入憑證（Token）的另一把金鑰。

**生成方式：**
```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

把輸出值替換 `REPLACE_WITH_64_BYTE_RANDOM_HEX`

---

#### 🔑 POSTGRES_PASSWORD — 資料庫密碼

**說明：** 本機測試用的資料庫密碼，自行設定一個即可（例如 `MyLocalTest2026`）。

把 `REPLACE_WITH_STRONG_PASSWORD` 替換為你設定的密碼。

> ⚠️ **重要：** `DATABASE_URL` 這一行裡的密碼也要同步修改。找到這一行：
> ```
> DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}
> ```
> 這行使用變數代入，只要你改了 `POSTGRES_PASSWORD` 就會自動生效，**不需要手動修改 DATABASE_URL**。

---

#### 🔑 OCR 設定（Google Document AI）— 測試時可跳過

**說明：** 系統使用 Google 的 AI 服務來讀取 PDF 表格。  
**如果你沒有 GCP 帳號**，可以先把這三行的值留空或填入假值 — 系統會自動切換到本機備援 OCR（準確度較低，但足以測試流程）：

```
GOOGLE_DOC_AI_PROJECT_ID=test-only
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=test-only
```

**如果你有 GCP 帳號**，請參考 [附錄 A：取得 Google Document AI 金鑰](#附錄-a取得-google-document-ai-金鑰)。

---

#### ✅ 本機測試的最終 .env 設定範例

以下是一個可以直接用於本機測試的完整範例（請替換 `SECRET_KEY` 和 `JWT_SECRET_KEY`）：

```dotenv
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=【貼上你用 python 生成的 token_hex(32) 值】
ALLOWED_HOSTS=localhost,127.0.0.1

CORS_ORIGINS=http://localhost:5173
CORS_ALLOW_CREDENTIALS=true

JWT_SECRET_KEY=【貼上你用 python 生成的 token_hex(64) 值】
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=ieepa_refund_db
POSTGRES_USER=ieepa_app
POSTGRES_PASSWORD=MyLocalTest2026
DATABASE_URL=postgresql+asyncpg://ieepa_app:MyLocalTest2026@db:5432/ieepa_refund_db

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_URL=redis://:@redis:6379/0
CELERY_BROKER_URL=redis://:@redis:6379/0
CELERY_RESULT_BACKEND=redis://:@redis:6379/0
CACHE_TTL_SECONDS=3600

DATA_ROOT=/data
UPLOAD_DIR=/data/uploads
REPORTS_DIR=/data/reports
KEYS_DIR=/data/keys
FERNET_KEY_PATH=/data/keys/app_secret.key
MAX_UPLOAD_SIZE_MB=20
ALLOWED_EXTENSIONS=pdf,jpg,jpeg,png
DOWNLOAD_TOKEN_EXPIRE_MINUTES=15

GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google_service_account.json
GOOGLE_DOC_AI_PROJECT_ID=test-only
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=test-only
TESSERACT_CMD=/usr/bin/tesseract
OCR_FALLBACK_ENABLED=true
OCR_CONFIDENCE_THRESHOLD=0.80

SMTP_HOST=mailhog
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=false
SMTP_FROM_ADDRESS=noreply@ieepa.dimerco.com
SMTP_FROM_NAME=Dimerco IEEPA Portal

RATE_LIMIT_UPLOAD=10/hour
RATE_LIMIT_CALCULATE=10/minute
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_GET=60/minute

ENABLE_CRM_SYNC=false
CRM_WEBHOOK_URL=
CRM_API_KEY=

ENABLE_BULK_UPLOAD=true

FILE_CLEANUP_TTL_HOURS=24
REPORT_CLEANUP_TTL_DAYS=90
CLEANUP_SCHEDULE_CRON=0 * * * *

GA4_MEASUREMENT_ID=G-XXXXXXXXXX
```

編輯完成後，**儲存檔案並關閉編輯器**。

---

## 4. 產生加密金鑰

> **用途：** 這把金鑰用來加密所有上傳的文件和個人資料，是系統安全的核心。只需要生成一次。

### 4.1 安裝 Python 套件

```bash
pip install cryptography
```

### 4.2 執行金鑰生成腳本

確認你在 `ieepa-refund-calculator` 資料夾內，然後執行：

```bash
python init_keys.py
```

**預期輸出：**
```
✅  Fernet key generated: data/keys/app_secret.key
    Size : 44 bytes (base64url-encoded 32-byte AES-256 key)

⚠️  ACTION REQUIRED:
   1. Verify permissions: ls -la data/keys/
   2. Back up 'data/keys/app_secret.key' to a secure offline location immediately.
   3. Never commit this file to version control (.gitignore covers data/keys/).
```

> ✅ 金鑰檔案已自動建立在 `data/keys/app_secret.key`  
> ⚠️ **請備份這個檔案！** 如果遺失，所有加密的上傳文件將無法解密。

---

## 5. 啟動所有服務

> 這一步會啟動系統所需的後端服務：API、Celery Worker、資料庫、Redis 快取、Email 測試伺服器。前端開發伺服器請另行啟動（見步驟 5.3）。

### 5.1 確認 Docker Desktop 正在執行

確認桌面工具列有 Docker 鯨魚圖示，且狀態為 **Running**。

### 5.2 啟動所有服務

在命令視窗中（確認你在 `ieepa-refund-calculator` 資料夾）執行：

```bash
docker compose up -d
```

**第一次執行會需要 5–15 分鐘**（需要下載基礎映像檔），之後再執行只需 30 秒。

**預期輸出（類似）：**
```
[+] Running 7/7
 ✔ Network ieepa-refund-calculator_default  Created
 ✔ Container ieepa-refund-calculator-db-1       Started
 ✔ Container ieepa-refund-calculator-redis-1    Started
 ✔ Container ieepa-refund-calculator-mailhog-1  Started
 ✔ Container ieepa-refund-calculator-api-1      Started
 ✔ Container ieepa-refund-calculator-worker-1   Started
 ✔ Container ieepa-refund-calculator-beat-1     Started
```

### 5.3 啟動前端開發伺服器（另開終端機視窗）

前端不透過 Docker 執行，需在本機使用 Node.js 啟動：

```bash
cd frontend
npm install      # 首次執行才需要（安裝 npm 套件）
npm run dev
```

前端伺服器啟動後，前往 **http://localhost:5173** 即可看到介面。

> 💡 Vite 開發伺服器會自動將 `/api/*` 請求代理至 `http://localhost:8000`，不需要額外設定。

### 5.4 查看服務狀態

```bash
docker compose ps
```

所有服務的 **STATUS** 欄位都應顯示 `Up` 或 `running`。

## 6. 建立資料庫結構

> 這一步會在資料庫中建立所有需要的資料表，只需要在**第一次啟動時執行一次**。

```bash
docker compose exec api alembic upgrade head
```

**預期輸出：**
```
INFO  [alembic.runtime.migration] Context impl PostgreSQLImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
```

> ✅ 如果看到 `Running upgrade` 表示成功建立資料表

---

## 7. 確認服務是否正常運作

### 7.1 確認 API 服務

開啟瀏覽器，前往：**http://localhost:8000/health**

應看到：
```json
{"status": "ok"}
```

### 7.2 確認 API 文件介面

前往：**http://localhost:8000/api/docs**

應看到 **Swagger UI** 互動式文件介面，列出所有 API 端點。

### 7.3 確認前端介面

前往：**http://localhost:5173**

應看到 IEEPA Tariff Refund Calculator 的首頁介面。

### 7.4 確認 Email 測試介面（MailHog）

前往：**http://localhost:8025**

這是一個假的 Email 收件匣，系統寄出的所有 Email 都會出現在這裡（不會真的寄出）。

### 7.5 服務清單總覽

| 服務 | 網址 | 說明 |
|------|------|------|
| 前端介面 | http://localhost:5173 | 使用者操作的主畫面 |
| API 後端 | http://localhost:8000 | 後端 REST API |
| API 文件 | http://localhost:8000/api/docs | 互動式 API 測試介面 |
| 健康檢查 | http://localhost:8000/health | 確認 API 是否正常 |
| Email 收件匣 | http://localhost:8025 | 查看系統寄出的 Email |

---

## 8. 執行第一次測試上傳

> 以下提供兩種測試方式：使用前端介面（推薦）或直接使用 API 文件。

### 8.1 透過前端介面測試（推薦）

確認前端伺服器已啟動（步驟 5.3），前往 **http://localhost:5173**。

完整流程共三步驟：

#### 步驟一：上傳 PDF
1. 在首頁點選 **「Start Calculation」**（或導覽至 `/calculate`）
2. 勾選隱私權同意選項
3. 將 CBP Form 7501 PDF 拖曳至上傳區域（`7501Samples/` 資料夾內有範例檔案）
4. 點選 **「Start Calculation」**
5. 系統會自動開始 OCR 讀取，並顯示進度動畫（通常需要 10–30 秒）

#### 步驟二：審核解析結果
- OCR 完成後，系統自動跳轉至 **審核頁面（/review）**
- 黃色（琥珀色）框標示信心度不足（< 80%）的欄位，請手動確認或修改
- 所有欄位確認正確後，點選 **「Confirm & Calculate」**

#### 步驟三：查看退稅結果
- 計算完成後，系統跳轉至 **結果頁面（/results/:id）**
- 頁面顯示：
  - 💰 預估 IEEPA 退稅金額
  - 退稅途徑徽章（PSC / PROTEST / INELIGIBLE）
  - 詳細關稅明細表（MFN / IEEPA / S301 / S232 / MPF / HMF）
  - 申請期限說明與操作建議
  - 法律免責聲明（必要，不可隱藏）

> ⚠️ **注意：** 若 `tariff_rates` 資料表中無對應的 HTS 稅率資料，IEEPA/MFN/S301/S232 金額將顯示為 $0.00。MPF 和 HMF 使用固定費率，計算不受影響。

---

### 8.2 透過 API 文件測試

> 開啟 **http://localhost:8000/api/docs**

#### 8.2.1 測試健康檢查

1. 在頁面上找到 `GET /health`
2. 點選它，再點 **"Try it out"**
3. 點 **"Execute"**
4. 應看到 **Response Code: 200** 和 `{"status": "ok"}`

#### 8.2.2 上傳 PDF 文件

1. 在頁面上找到 `POST /api/v1/documents/upload`
2. 點選，再點 **"Try it out"**
3. 填入以下欄位：
   - **file**：點選 **"Choose File"**，選擇一份 PDF（`7501Samples/` 內有範例）
   - **privacy_accepted**：輸入 `true`
   - **X-Idempotency-Key**（在 Header 區）：輸入任意不重複的字串，例如 `test-001`
4. 點選 **"Execute"**
5. 應看到 **Response Code: 202** 和類似以下的回應：
   ```json
   {
     "success": true,
     "data": {
       "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
       "status": "queued",
       "expires_at": "2026-03-05T10:00:00Z"
     }
   }
   ```
6. **複製** `job_id` 的值（你之後需要用到）

#### 8.2.3 查詢 OCR 處理狀態

1. 找到 `GET /api/v1/documents/{job_id}/status`
2. 點選，再點 **"Try it out"**
3. 在 `job_id` 欄位貼入剛才複製的 ID
4. 點 **"Execute"**
5. 回應的 `status` 欄位會顯示：
   - `queued` — 排隊等待中
   - `processing` — OCR 讀取中
   - `completed` — 處理完成（可以看到解析出的欄位）
   - `review_required` — 部分欄位信心度不足，需要人工確認
   - `failed` — 處理失敗（通常是文件格式問題）

> 💡 等待 10–30 秒後再查詢，讓 OCR 有時間處理

#### 8.2.4 觸發退稅計算

當狀態為 `completed` 或 `review_required` 後：

1. 找到 `POST /api/v1/documents/{job_id}/calculate`
2. 點選，再點 **"Try it out"**
3. 填入 `job_id` 並在 Header 加入 `X-Idempotency-Key: calc-test-001`
4. 點 **"Execute"**
5. 應看到 **Response Code: 202** 和 `{ "calculation_id": "..." }`
6. 複製 `calculation_id`

#### 8.2.5 取得計算結果

1. 找到 `GET /api/v1/results/{calculation_id}`
2. 貼入 `calculation_id`，點 **"Execute"**
3. 應看到完整的退稅明細，包含 `estimated_refund`、`refund_pathway`、`tariff_lines` 等

### 8.3 查看服務執行日誌

如果遇到問題，可以查看各服務的日誌：

```bash
# 查看 API 服務日誌
docker compose logs api --tail=50

# 查看 Celery Worker 日誌（OCR 工作執行在這裡）
docker compose logs worker --tail=50

# 即時追蹤日誌（按 Ctrl+C 停止）
docker compose logs -f api worker
```

---

## 9. 停止服務

當你測試完畢，可以用以下指令停止所有服務：

```bash
# 停止服務（保留資料，下次啟動仍存在）
docker compose stop

# 停止並移除服務（資料庫資料會清空）
docker compose down

# 停止並移除所有資料（完全重置，慎用）
docker compose down -v
```

下次要重新啟動時，只需：
```bash
docker compose up -d
```
（不需要重新執行 `alembic upgrade head`，資料庫結構已保留）

---

## 10. 常見問題排解

### ❌ 問題：`docker compose up` 時出現「port is already in use」

**原因：** 你電腦上某個程式已佔用了需要的 Port（通常是 8000、5432 或 6379）。

**解決方式：**
1. 找出占用 Port 的程式（以 Port 8000 為例）：

   **Windows：**
   ```cmd
   netstat -ano | findstr :8000
   ```
   
   **Mac：**
   ```bash
   lsof -i :8000
   ```
2. 記下 PID（最右欄的數字），在工作管理員（Windows）或 `kill <PID>`（Mac）結束該程式
3. 再次執行 `docker compose up -d`

---

### ❌ 問題：`docker compose exec api alembic upgrade head` 失敗

**原因：** 資料庫可能還沒完全啟動完成。

**解決方式：** 等待 30 秒後再試：
```bash
docker compose ps   # 確認 db 的 STATUS 是 Up (healthy)
docker compose exec api alembic upgrade head
```

---

### ❌ 問題：上傳 PDF 後 status 一直停在 `queued` 或 `processing`

**原因：** Celery Worker 可能未正常啟動。

**解決方式：**
```bash
docker compose logs worker --tail=50
```
查看是否有 `ERROR` 訊息。常見原因：
- Redis 連線失敗 → 確認 `docker compose ps` 中 `redis` 服務是 `Up`
- OCR 套件問題 → 查看具體錯誤訊息

---

### ❌ 問題：Docker Desktop 無法啟動（Windows）

**解決方式：**
1. 確認 Windows 版本為 Windows 10 64-bit Build 19041 或以上
2. 開啟「控制台 → 程式和功能 → 開啟或關閉 Windows 功能」，確認以下項目已勾選：
   - **Hyper-V**（或 WSL 2）
   - **Windows 子系統 Linux 版**
3. 重新啟動電腦後再試

---

### ❌ 問題：`python init_keys.py` 顯示「No module named cryptography」

**解決方式：**
```bash
pip install cryptography
python init_keys.py
```

---

### ❌ 問題：`http://localhost:5173` 無法開啟（前端）

**原因：** 前端 Vite 開發伺服器尚未啟動（前端不在 Docker 中執行，需另行啟動）。

**解決方式：** 開啟新的終端機視窗，執行：
```bash
cd frontend
npm install      # 若尚未安裝套件
npm run dev
```
等待 Vite 顯示 `VITE ready in ... ms` 後再重新整理頁面。

若執行 `npm install` 時出錯，請確認：
- Node.js 已安裝（`node --version` 應顯示 v18 以上）
- 你在 `ieepa-refund-calculator/frontend/` 資料夾內

---

### ❌ 問題：點選「Confirm & Calculate」顯示「Failed to submit. Please try again.」

**原因：** 文件狀態不符（非 `completed` 或 `review_required`），或 OCR 尚未完成。

**解決方式：**
1. 確認 `GET /api/v1/documents/{job_id}/status` 回應的 `status` 為 `completed` 或 `review_required`
2. 若狀態仍為 `queued`，查看 Worker 日誌：`docker compose logs worker --tail=50`
3. 若狀態為 `failed`，請重新上傳文件

---

### 💡 查看所有服務的即時狀態

```bash
docker compose ps
```

所有 STATUS 都應為 `Up` 或 `running`。如果某個服務是 `Exit`，執行：
```bash
docker compose logs <服務名稱>
```
例如：`docker compose logs api`

---

## 附錄 A：取得 Google Document AI 金鑰

> 此步驟為選填。不設定時，系統自動使用本機 OCR（pytesseract），準確度約 60–70%。
> 設定 Google Document AI 可提升準確度至 90%+。

### A.1 建立 GCP 專案

1. 前往：**https://console.cloud.google.com/**
2. 點選上方專案下拉選單 → **「新增專案」**
3. 輸入專案名稱（例如 `dimerco-ieepa-test`），點選**建立**
4. 記下 **Project ID**（格式類似 `dimerco-ieepa-test-123456`）

### A.2 啟用 Document AI API

1. 前往：**https://console.cloud.google.com/apis/library/documentai.googleapis.com**
2. 點選 **「啟用」**

### A.3 建立 Form Parser 處理器

1. 前往：**https://console.cloud.google.com/ai/document-ai/processors**
2. 點選 **「建立處理器」**
3. 選擇 **「Form Parser」**
4. 輸入名稱，區域選擇 **「us（美國）」**，點選**建立**
5. 記下 **Processor ID**（顯示在處理器詳細頁面）

### A.4 建立服務帳戶金鑰

1. 前往：**https://console.cloud.google.com/iam-admin/serviceaccounts**
2. 點選 **「建立服務帳戶」**
3. 輸入名稱（例如 `ieepa-docai`），點選**建立並繼續**
4. 角色選擇 **「Document AI → Document AI Editor」**，點選**繼續 → 完成**
5. 點選剛建立的服務帳戶 → **「金鑰」標籤 → 新增金鑰 → 建立新的金鑰 → JSON**
6. 下載 JSON 檔案，重新命名為 `google_service_account.json`
7. 將此檔案放置於專案的 `backend/credentials/` 資料夾（需自行建立此資料夾）

### A.5 更新 .env

在 `backend/.env` 中更新以下三個值：
```dotenv
GOOGLE_DOC_AI_PROJECT_ID=【你的 Project ID】
GOOGLE_DOC_AI_LOCATION=us
GOOGLE_DOC_AI_PROCESSOR_ID=【你的 Processor ID】
```

同時更新 `docker-compose.yml` 中 `api` 和 `worker` 服務，加入 `credentials` 資料夾掛載：
```yaml
volumes:
  - ./backend:/app
  - ./data:/data
  - ./backend/credentials:/app/credentials:ro  # 新增這行
```

重新啟動服務：
```bash
docker compose down && docker compose up -d
```

---

## 附錄 B：快速指令速查表

| 目的 | 指令 |
|------|------|
| 啟動所有後端服務 | `docker compose up -d` |
| 啟動前端開發伺服器 | `cd frontend && npm run dev` |
| 停止服務（保留資料） | `docker compose stop` |
| 停止並清除容器 | `docker compose down` |
| 查看所有服務狀態 | `docker compose ps` |
| 查看 API 日誌 | `docker compose logs api --tail=50` |
| 查看 Worker 日誌 | `docker compose logs worker --tail=50` |
| 即時追蹤日誌 | `docker compose logs -f api worker` |
| 執行資料庫 Migration | `docker compose exec api alembic upgrade head` |
| 重建所有映像檔 | `docker compose build --no-cache` |
| 完全重置（清空資料） | `docker compose down -v` |
| 前端型別檢查 | `cd frontend && npx tsc --noEmit` |
| 執行前端測試 | `cd frontend && npm run test` |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.1 | March 2026 | Internal — Confidential*
