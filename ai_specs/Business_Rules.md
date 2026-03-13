# Business Rules & Workflow
**Document Reference:** DMX-TRS-IEEPA-2026-001  
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Section 5.1 — Business Rules (BR-xx)

以下業務規則為系統計算引擎的核心邏輯，源自 CALC-001 ~ CALC-009 及相關系統需求。所有規則均**不可協商（MUST）**，任何偏離需經過正式變更申請。

---

### BR-001：IEEPA 關稅適用範圍

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-001 |
| **規則名稱** | IEEPA 關稅適用性判斷 |
| **條件** | HTS Code 開頭為 9903.01 或 9903.02 且稅額 > 0 的行項目且 `summary_date` 在 IEEPA 生效日期區間內 |
| **動作** | 計算 IEEPA 關稅：`entered_value × ieepa_rate` |
| **例外** | 非中國原產地（non-CN）一律回傳 IEEPA 關稅 = $0.00 |
| **參考來源** | CALC-002 |

---

### BR-002：基礎 MFN 關稅計算

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-002 |
| **規則名稱** | Most Favored Nation (MFN) 稅率計算 |
| **公式** | `mfn_tariff = entered_value × mfn_rate` |
| **稅率來源** | 依據 `(hts_code, country_of_origin, summary_date)` 查詢 `tariff_rates` 資料表中 `tariff_type = 'MFN'` 的適用稅率 |
| **驗證基準** | 對照 CBP CROSS 資料，20 筆測試報關單，差異 ≤ 0.01% |
| **參考來源** | CALC-001 |

---

### BR-003：Section 301 關稅計算

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-003 |
| **規則名稱** | Section 301 關稅（美中貿易戰附加稅）|
| **清單分類** | 依 HTS 代碼識別所屬清單：List 1 / List 2 / List 3A / List 3B / List 4A / List 4B |
| **公式** | `s301_tariff = entered_value × s301_rate` |
| **驗證基準** | 對照 USTR 資料，20 筆測試 HTS 代碼分類結果須 100% 正確 |
| **參考來源** | CALC-003 |

---

### BR-004：Section 232 關稅計算（鋼鐵/鋁）

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-004 |
| **規則名稱** | Section 232 鋼鐵/鋁製品附加稅 |
| **條件** | 僅適用於鋼鐵或鋁衍生品的 HTS 代碼（系統維護白名單）|
| **旗標** | 回應物件需包含 `section_232_applicable: true/false` |
| **公式** | `s232_tariff = entered_value × s232_rate`（如適用）|
| **參考來源** | CALC-004 |

---

### BR-005：MPF（商品處理費）計算

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-005 |
| **規則名稱** | Merchandise Processing Fee (MPF) |
| **公式** | `mpf = total_entered_value × 0.3464%` |
| **下限（Floor）** | $32.71 USD（低於此值取 $32.71）|
| **上限（Cap）** | $634.62 USD（高於此值取 $634.62）|
| **驗證要求** | 邊界值測試：恰好等於、略低於、略高於上下限時均須回傳正確數值 |
| **參考來源** | CALC-005 |

---

### BR-006：HMF（港口維護費）計算

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-006 |
| **規則名稱** | Harbor Maintenance Fee (HMF) |
| **條件** | 僅適用於海運（`mode_of_transport = 'vessel'`）|
| **公式** | `hmf = total_entered_value × 0.125%` |
| **例外** | 空運（air cargo）一律回傳 HMF = $0.00 |
| **參考來源** | CALC-006 |

---

### BR-007：退稅途徑判斷

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-007 |
| **規則名稱** | 退稅途徑（Refund Pathway）決策 |
| **計算方式** | `days_elapsed = current_date − summary_date` |

| `days_elapsed` 範圍 | `refund_pathway` | 說明 |
|----------------------|------------------|------|
| ≤ 15 天 | `PSC` | Post-Summary Correction，最簡便快速 |
| 16 ~ 180 天 | `PROTEST` | CBP Protest，較複雜但仍可申請 |
| > 180 天 | `INELIGIBLE` | 超過時效，無法申請退稅 |

| **邊界值測試** | 第 15 天 → PSC；第 16 天 → PROTEST；第 180 天 → PROTEST；第 181 天 → INELIGIBLE |
| **參考來源** | CALC-007 |

---

### BR-008：退稅金額估算

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-008 |
| **規則名稱** | 估算退稅金額 |
| **公式** | `estimated_refund = Σ ieepa_tariff_per_line_item` （所有 HTS 行項目的 IEEPA 關稅加總）|
| **驗證基準** | 由持牌 CHB 手工計算 10 筆真實報關單，系統結果差異 ≤ 2% |
| **備注** | IEEPA 退稅不包含 MFN、S301、S232、MPF 或 HMF |
| **參考來源** | CALC-008 |

---

### BR-009：稅率查詢規則

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-009 |
| **規則名稱** | 稅率資料庫查詢邏輯 |
| **查詢 Key** | `(hts_code, country_of_origin, tariff_type, summary_date)` |
| **SQL 條件** | `WHERE hts_code=$1 AND country_code=$2 AND tariff_type=$3 AND effective_from<=$4 AND (effective_to IS NULL OR effective_to>=$4)` |
| **說明** | 查詢以**報關單日期（summary_date）**為基準的適用稅率，`effective_to IS NULL` 表示目前仍有效的稅率 |
| **參考來源** | Section 6.2 |

---

### BR-010：OCR 信心度閾值

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-010 |
| **規則名稱** | OCR 欄位信心度判斷 |
| **閾值** | 信心分數 < 0.80（即 80%）|
| **動作** | 該欄位標記為 `review_required: true`，前端以琥珀色（Amber）邊框高亮顯示，要求使用者確認或修正 |
| **文件辨識失敗** | 若整份文件信心度 < 0.50，回傳 `UNRECOGNISED_DOCUMENT` 錯誤，拒絕進行計算 |
| **Fallback** | Google Document AI 失敗或信心度 < 0.50 時，自動切換至 AWS Textract |
| **參考來源** | OCR-003, OCR-007 |

---

### BR-011：計算稽核軌跡

| 項目 | 內容 |
|------|------|
| **規則 ID** | BR-011 |
| **規則名稱** | 計算結果稽核軌跡不可變 |
| **要求** | 每次計算須在 `calculation_audit` 資料表建立一筆不可刪除的記錄，包含：所有輸入值、所有稅率查詢結果、所有中間計算值 |
| **目的** | 確保計算結果可被事後重現驗證，符合海關申報可追溯性要求 |
| **參考來源** | CALC-009 |

---

## Section 5.2 — Workflow（作業流程）

### 5.2.1 主要使用者流程（Single Entry）

```
┌─────────────────────────────────────────────────────────────────┐
│                       使用者端 (Browser)                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 1：上傳文件
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/v1/documents/upload                                   │
│  • 驗證 MIME type + Magic Bytes（非副檔名）                       │
│  • 檔案上傳至 S3（AES-256 SSE-KMS 加密，24h TTL）                │
│  • 觸發非同步 OCR Job，回傳 { job_id, status: "queued" }         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 2：OCR 處理（非同步）
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Celery Worker — OCR Job                                         │
│  • 主要引擎：Google Document AI (Form Parser)                    │
│  • 備用引擎：AWS Textract（主引擎失敗或整體信心 < 0.50 時觸發）   │
│  • 提取至少 20 個命名欄位（Box 1, 2, 3, 5, 11, 14, 29, 31...）  │
│  • 每欄位附帶信心分數（0.0 ~ 1.0）                               │
│  • 信心 < 0.80 的欄位標記 review_required: true                  │
│  • 狀態更新：queued → processing → review_required / completed   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 3：使用者審查（/review 頁）
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  GET /api/v1/documents/{job_id}/status（輪詢直到完成）            │
│  • 前端顯示所有提取欄位及信心分數                                  │
│  • review_required 欄位顯示琥珀色警告，允許內聯編輯               │
│  PATCH /api/v1/documents/{job_id}/fields（使用者修正）            │
│  • 儲存使用者手動修正至 user_corrections（JSONB）                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 4：觸發計算
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/v1/documents/{job_id}/calculate                       │
│  • 以最終欄位值（含使用者修正）觸發計算引擎                        │
│  • 回傳 { calculation_id }，計算非同步執行                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 5：計算引擎執行（非同步）
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  Celery Worker — Calculation Engine                              │
│                                                                   │
│  For each HTS line item:                                         │
│    ① 查詢 tariff_rates: (hts_code, country_code, tariff_type,   │
│       summary_date) → 取得各類稅率                                │
│    ② BR-002: 計算 MFN 基本稅                                     │
│    ③ BR-001: 計算 IEEPA 稅（僅 CN 原產地）                       │
│    ④ BR-003: 計算 S301 稅（依 HTS 清單分類）                     │
│    ⑤ BR-004: 判斷並計算 S232 稅（鋼鐵/鋁）                      │
│  全部行項目：                                                     │
│    ⑥ BR-005: 計算 MPF（含上下限）                                │
│    ⑦ BR-006: 計算 HMF（僅海運）                                  │
│    ⑧ BR-008: 加總 estimated_refund = Σ IEEPA                    │
│    ⑨ BR-007: 判斷 refund_pathway（PSC / PROTEST / INELIGIBLE）  │
│    ⑩ BR-011: 寫入 calculation_audit（不可刪除）                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 6：顯示結果（/results/:id 頁）
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  GET /api/v1/results/{calculation_id}                            │
│  • 顯示關稅組成明細表（MFN / IEEPA / S301 / S232 / MPF / HMF）  │
│  • IEEPA 行以視覺高亮標示                                         │
│  • 退稅金額以大字體顯示於醒目區塊                                  │
│  • 退稅途徑（PSC / PROTEST / INELIGIBLE）及說明顯示於結果下方     │
│  • 強制顯示法律免責聲明（不可隱藏）                                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
         STEP 7：PDF 匯出 / 潛客捕捉
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  POST /api/v1/results/{calculation_id}/export                    │
│  • 觸發伺服器端 PDF 產製（含 Dimerco 品牌、退稅明細、後續步驟）   │
│  • PDF 存至 S3，回傳 15 分鐘有效期的 Pre-signed URL              │
│                                                                   │
│  POST /api/v1/leads（/register 頁）                              │
│  • 使用者填寫：姓名、公司、Email、電話、國家                       │
│  • PII 欄位（email, phone, full_name）應用層 AES-256 加密後儲存  │
│  • 非同步觸發 CRM 同步（Celery Worker）                          │
│  • CRM 同步失敗：指數退避重試（1分鐘 → 5分鐘 → 30分鐘）         │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5.2.2 批量上傳流程（Bulk Upload — 已登入使用者）

```
[已登入使用者]
    │
    ▼
POST /api/v1/bulk/upload
    • 接受 CSV / XLSX（包含多筆 Entry Summary 資料）
    • 驗證欄位結構（依範本 Schema 檢查）
    • 每列建立獨立計算 Job → 回傳 bulk_job_id
    │
    ▼
GET /api/v1/bulk/{bulk_job_id}/status（輪詢）
    • 回傳 { total, completed, failed, in_progress, results_preview[] }
    │
    ▼
GET /api/v1/bulk/{bulk_job_id}/results
    • 完整結果陣列
    • 包含彙整值：total_refundable（所有行項目退稅加總）
```

---

### 5.2.3 管理員稅率更新流程（Admin Rate Management）

```
[Admin User]
    │
    ├─ 單筆更新：PUT /api/v1/admin/rates/{hts_code}
    │       • 驗證稅率為正小數
    │       • 記錄至 audit_log（含管理員 ID + 時間戳）
    │       • 立即清除 Redis 快取（ieepa_rate 相關 key）
    │
    └─ 批量匯入：POST /api/v1/admin/rates/import
            • 接受 CSV：hts_code, country_code, tariff_type, rate, effective_date
            • 回傳匯入摘要（成功筆數 / 失敗筆數）
```

---

### 5.2.4 錯誤處理流程（Error Handling）

| 錯誤情境 | 系統行為 | 使用者訊息 |
|----------|----------|-----------|
| 檔案格式不符（非 PDF/JPEG/PNG）| HTTP 415，拒絕上傳 | 友善提示可接受格式 |
| 文件辨識失敗（信心 < 0.50）| 回傳 `UNRECOGNISED_DOCUMENT` | 說明原因並引導重新上傳 |
| OCR 超時（> 30 秒）| Job status → `failed` | 顯示錯誤訊息，提供 Retry 按鈕 |
| 稅率查無資料 | 對應稅項回傳 $0，標記警告 | 警示說明該稅項無法計算 |
| CRM 同步失敗（3次重試後）| `crm_sync_status = 'failed'`，觸發告警 | 使用者端不感知，後台告警通知 |
| Rate Limit 超過 | HTTP 429 + `Retry-After` Header | 友善說明請稍後再試 |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
