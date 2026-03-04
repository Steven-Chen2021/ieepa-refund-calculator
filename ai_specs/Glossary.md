# Glossary — 名詞解釋與狀態碼定義
**Document Reference:** DMX-TRS-IEEPA-2026-001  
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Appendix A1 — Logistics & Technical Glossary（物流與技術名詞解釋）

### A1.1 法規與關稅術語

| 縮寫 / 術語 | 全名 | 中文說明 |
|-------------|------|---------|
| **IEEPA** | International Emergency Economic Powers Act | 《國際緊急經濟權力法》。美國總統依此法令對中國商品加徵的額外關稅，為本系統計算的核心退稅標的。 |
| **CBP** | U.S. Customs and Border Protection | 美國海關及邊境保衛局。負責進口報關核審、關稅徵收及貿易法規執行。 |
| **CHB** | Customs House Broker | 持牌報關行。由 CBP 授權代理進口商辦理清關手續的專業人員。 |
| **HTS** | Harmonized Tariff Schedule | 美國協調關稅稅則。10 位數的商品分類代碼，用於確定適用關稅稅率。 |
| **MFN** | Most Favored Nation tariff rate | 最惠國稅率。依 WTO 規則對會員國商品適用的基準關稅稅率，不考慮任何附加稅。 |
| **MPF** | Merchandise Processing Fee | 商品處理費。CBP 收取的行政費用，費率為 0.3464%，下限 $32.71，上限 $634.62 USD。 |
| **HMF** | Harbor Maintenance Fee | 港口維護費。費率為 0.125%，僅適用於海運進口，空運免收。 |
| **Section 301** | Section 301 of the Trade Act of 1974 | 第 301 條關稅。美中貿易戰期間 USTR 對中國商品加徵的額外關稅，依 HTS 代碼歸入 List 1/2/3A/3B/4A/4B。 |
| **Section 232** | Section 232 of the Trade Expansion Act of 1962 | 第 232 條關稅。基於國家安全理由對鋼鐵及鋁製品加徵的附加稅。 |
| **PSC** | Post-Summary Correction | 報關單後更正。進口商於 Entry Summary 提交後 15 天內，向 CBP 申請修正報關資料的機制。本系統中為「最佳退稅途徑」（時效最短）。 |
| **Protest** | CBP Protest | 抗議申請。進口商在 180 天內向 CBP 提出的正式申訴，適用於已超過 PSC 時效但仍在 180 天內的案例。 |
| **CBP Form 7501** | Entry Summary | 進口報關彙總表。進口商向 CBP 申報的核心文件，載明：進口商、原產地、HTS 代碼、申報值、關稅計算等資訊。本系統 OCR 的主要輸入文件。 |
| **Entry Number** | — | 報關單號碼。格式為英數字 11 碼，例如：`XXX-1234567-8`，為每筆進口清關的唯一識別碼。 |
| **Country of Origin** | — | 原產地國。使用 ISO 3166-1 alpha-2 代碼（例：CN = 中國、TW = 台灣、VN = 越南）。IEEPA 關稅僅適用於 CN。 |
| **Entered Value** | — | 申報價值（美元）。進口商申報的商品交易價格，為各類關稅計算的基礎數值。 |
| **Summary Date** | — | 報關單日期。CBP Form 7501 的申報日期，用於判斷適用稅率及計算退稅時效。 |
| **Duty Decomposition** | — | 關稅拆解。將進口商繳納的總關稅分解為各組成項目（MFN、IEEPA、S301、S232、MPF、HMF）的計算過程。 |
| **USTR** | U.S. Trade Representative | 美國貿易代表署。負責制定並公布 Section 301 關稅清單的政府機構。 |
| **Federal Register** | — | 聯邦公報。美國政府官方期刊，所有關稅稅率調整均在此公告，為稅率資料的法規引用來源（`source_ref`）。 |

---

### A1.2 系統與技術術語

| 縮寫 / 術語 | 全名 | 說明 |
|-------------|------|------|
| **ALB** | Application Load Balancer (AWS) | AWS 應用程式負載平衡器，負責 HTTPS 流量分配至 API 容器。 |
| **CDN** | Content Delivery Network | 內容傳遞網路。本系統使用 AWS CloudFront 提供全球節點，加速前端靜態資源載入。 |
| **CSP** | Content Security Policy | 內容安全政策。瀏覽器安全機制，防止 XSS 攻擊。 |
| **ECS** | Elastic Container Service (AWS) | AWS 容器服務，本系統 API Server 以 Fargate 無伺服器模式部署。 |
| **JWT** | JSON Web Token | JSON 網路令牌。用於 API 身份驗證，Access Token 有效期 15 分鐘，Refresh Token 有效期 7 天。 |
| **OCR** | Optical Character Recognition | 光學字元辨識。本系統使用 Google Document AI 作為主要 OCR 引擎，AWS Textract 作為備援。 |
| **ORM** | Object-Relational Mapper | 物件關聯映射器。本系統使用 SQLAlchemy 2.0（async），所有查詢均透過 ORM 參數化，避免 SQL 注入。 |
| **RDS** | Relational Database Service (AWS) | AWS 關聯式資料庫服務。本系統使用 PostgreSQL 15，Multi-AZ 高可用部署。 |
| **SPA** | Single-Page Application | 單頁應用程式。本系統前端以 React 18 建置，透過 API 動態載入資料，無須完整換頁。 |
| **SSE-KMS** | Server-Side Encryption with AWS KMS | 使用 AWS 金鑰管理服務的伺服器端加密。所有上傳至 S3 的文件均以此方式加密儲存。 |
| **TTL** | Time-To-Live | 存活時間。上傳的 Form 7501 文件在 S3 的保存期限為 24 小時，到期自動刪除。 |
| **WAF** | Web Application Firewall | Web 應用程式防火牆。本系統部署 AWS WAF，套用 OWASP Top 10 規則集及速率限制。 |
| **Pre-signed URL** | — | 預簽名 URL。S3 產生的臨時存取連結，有效期 15 分鐘，用於 PDF 報告下載。到期後回傳 HTTP 403。 |
| **Celery** | — | Python 分散式任務佇列。本系統用於非同步執行 OCR Job、計算 Job 及 CRM 同步任務，以 Redis 作為 Broker。 |
| **Exponential Backoff** | — | 指數退避重試。CRM 同步失敗時的重試策略：第 1 次失敗後等 1 分鐘、第 2 次 5 分鐘、第 3 次 30 分鐘，3 次後標記失敗。 |

---

## Appendix A2 — Status Codes（狀態碼定義）

### A2.1 文件處理狀態（Document Processing Status）

適用範圍：`documents.status` 欄位、`GET /api/v1/documents/{job_id}/status` 回應。

| 狀態碼 | 值 | 說明 | 下一狀態 |
|--------|-----|------|---------|
| **QUEUED** | `"queued"` | 文件已上傳至 S3，OCR Job 已排入佇列，等待 Worker 取件 | `processing` |
| **PROCESSING** | `"processing"` | OCR Worker 正在處理文件（呼叫 Google Document AI 或 Textract）| `review_required` / `completed` / `failed` |
| **REVIEW_REQUIRED** | `"review_required"` | OCR 完成，但存在 1 個以上信心分數 < 0.80 的欄位，需使用者人工確認 | `completed`（使用者確認後）|
| **COMPLETED** | `"completed"` | OCR 完成且所有欄位信心度達標（或使用者已完成修正），可進行計算 | （終態，觸發計算）|
| **FAILED** | `"failed"` | OCR 處理失敗（超時、引擎錯誤、或文件整體信心 < 0.50 — `UNRECOGNISED_DOCUMENT`）| （終態，需重新上傳）|

---

### A2.2 計算工作狀態（Calculation Job Status）

適用範圍：`calculations.status` 欄位。

| 狀態碼 | 值 | 說明 |
|--------|-----|------|
| **PENDING** | `"pending"` | 計算 Job 已建立，等待 Worker 執行 |
| **CALCULATING** | `"calculating"` | 計算 Worker 正在執行稅率查詢及各項計算 |
| **COMPLETED** | `"completed"` | 計算完成，結果已寫入 `calculations` 資料表，可供查詢 |
| **FAILED** | `"failed"` | 計算失敗（例：稅率資料缺失、計算溢位），需通知管理員 |

---

### A2.3 退稅途徑代碼（Refund Pathway Codes）

適用範圍：`calculations.refund_pathway`、`GET /api/v1/results/{calculation_id}` 回應。

| 途徑代碼 | 值 | 適用條件 | 說明 |
|----------|-----|---------|------|
| **PSC** | `"PSC"` | `summary_date` 距今 ≤ 15 天 | Post-Summary Correction。進口商可直接向 CBP 提交更正，流程最簡便。**建議優先選擇。** |
| **PROTEST** | `"PROTEST"` | `summary_date` 距今 16 ~ 180 天 | CBP Protest（抗議申請）。需正式提交抗議文件，通常需要 CHB 或律師協助。 |
| **INELIGIBLE** | `"INELIGIBLE"` | `summary_date` 距今 > 180 天 | 已超過法定申請時效，無法申請 IEEPA 退稅。 |

---

### A2.4 CRM 同步狀態（CRM Sync Status）

適用範圍：`leads.crm_sync_status` 欄位。

| 狀態碼 | 值 | 說明 |
|--------|-----|------|
| **PENDING** | `"pending"` | 潛客資料已寫入 DB，CRM 同步 Job 已排入佇列 |
| **SYNCING** | `"syncing"` | Celery Worker 正在呼叫 CRM REST API |
| **SYNCED** | `"synced"` | 成功同步至 CRM，`crm_lead_id` 欄位已填入 CRM 系統的潛客 ID |
| **FAILED** | `"failed"` | 3 次重試後仍失敗（1m → 5m → 30m），觸發後台告警，需人工介入 |

---

### A2.5 OCR 特殊錯誤代碼（OCR Error Codes）

| 錯誤代碼 | 觸發條件 | HTTP 狀態碼 | 使用者端說明 |
|----------|---------|------------|-------------|
| `UNRECOGNISED_DOCUMENT` | 整份文件 OCR 信心度 < 0.50，系統無法辨識為有效的 CBP Form 7501 | 422 | 顯示說明訊息，引導使用者重新上傳清晰版本或手動輸入資料 |
| `UNSUPPORTED_FILE_TYPE` | 上傳的 MIME type 或 Magic Bytes 不符合 PDF / JPEG / PNG | 415 | 提示可接受的檔案格式 |
| `FILE_TOO_LARGE` | 檔案大小超過 20MB | 413 | 提示最大檔案限制 |
| `OCR_TIMEOUT` | OCR 處理時間超過 30 秒 | 504（非同步通知）| 顯示錯誤訊息，提供 Retry 按鈕 |

---

### A2.6 API 通用錯誤代碼（General API Error Codes）

| HTTP 狀態碼 | 意義 | 本系統使用情境 |
|-------------|------|--------------|
| `202 Accepted` | 請求已接受，非同步處理中 | 文件上傳、計算觸發 |
| `201 Created` | 資源建立成功 | 潛客資料提交 |
| `400 Bad Request` | 請求格式錯誤 | 缺少必填欄位、JSON 格式錯誤 |
| `403 Forbidden` | 無存取權限 | Pre-signed URL 過期（15 分鐘後）、非 Admin 存取 Admin API |
| `404 Not Found` | 資源不存在 | `job_id` 或 `calculation_id` 查無資料 |
| `413 Payload Too Large` | 檔案過大 | 上傳超過 20MB |
| `415 Unsupported Media Type` | 不支援的檔案類型 | 非 PDF/JPEG/PNG 的上傳 |
| `422 Unprocessable Entity` | 語義錯誤 | OCR 辨識失敗（`UNRECOGNISED_DOCUMENT`）|
| `429 Too Many Requests` | 超過速率限制 | 每 IP 每小時 10 次上傳、每 IP 每分鐘 60 次 GET |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
