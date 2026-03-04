# UI Specification
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On:** Project_Context.md · Business_Rules.md · Tech_Stack.md · Security_Spec.md  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Section 4.1 — Screen Inventory（頁面清單）

### 共用 UI 規範（Global UI Rules）

| 規則 | 說明 |
|------|------|
| **斷點** | `375px`（iPhone SE）/ `768px`（iPad）/ `1024px`（Laptop）/ `1440px`（Desktop）|
| **語系切換** | 右上角 Language Toggle：`EN` ↔ `中文`，所有字串外部化至 `i18n/{en,zh-CN}.json` |
| **字型** | 英文：Inter；中文：Noto Sans SC；等寬：JetBrains Mono（數字金額）|
| **色彩語意** | Primary Blue `#1E40AF`、Success Green `#16A34A`、Warning Amber `#D97706`、Error Red `#DC2626`、IEEPA Highlight `#FEF3C7`（淡黃）|
| **頂部導覽列** | 固定顯示：Dimerco Logo、語系 Toggle、登入/帳號狀態；高度 64px |
| **頁尾** | 免責聲明連結、隱私政策連結、版權聲明 |
| **無障礙** | WCAG 2.1 Level AA；所有互動元素具 ARIA label；Tab 鍵序正確 |
| **錯誤呈現** | 不顯示原始錯誤碼或 stack trace；每個錯誤狀態有專屬文案及 Retry / Contact Us 按鈕 |

---

### 4.1.1 Landing Page（首頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/` |
| **存取控制** | 公開 |
| **目的** | 行銷說明 + 引導使用者進入計算工具 |

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR  [Logo]                    [EN/中文]  [登入]          │
├──────────────────────────────────────────────────────────────┤
│  HERO SECTION                                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  大標題：Estimate Your IEEPA Tariff Refund             │  │
│  │  副標題：Upload your CBP Form 7501 and get an instant  │  │
│  │          itemised refund estimate in minutes.           │  │
│  │                                                         │  │
│  │  [▶ Start Calculating]  (Primary CTA Button)           │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  HOW IT WORKS（3 步驟說明）                                    │
│  [① Upload 7501]  [② Review & Confirm]  [③ Get Refund Est.]  │
├──────────────────────────────────────────────────────────────┤
│  TRUST INDICATORS                                              │
│  「Validated by Licensed CHB」「IEEPA Rate DB Updated」        │
│  「24h Document Auto-Deletion」「GDPR Compliant」              │
├──────────────────────────────────────────────────────────────┤
│  FOOTER                                                        │
└──────────────────────────────────────────────────────────────┘
```

**互動行為：**
- `[Start Calculating]` → 導向 `/calculate`
- 頁面無需 API 呼叫

---

### 4.1.2 Calculator Page（計算器／上傳頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/calculate` |
| **存取控制** | 公開 |
| **目的** | 上傳 CBP Form 7501，觸發 OCR 處理 |
| **狀態機** | `idle` → `privacy_accepted` → `uploading` → `processing` → `review_required` / `completed` / `failed` |

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR                                                        │
├──────────────────────────────────────────────────────────────┤
│  步驟指示器 ●──────○──────○                                    │
│             Upload  Review  Results                            │
├──────────────────────────────────────────────────────────────┤
│  隱私聲明區塊（COMP-001 — 上傳 UI 前強制顯示）                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  📋 Privacy Notice                                      │  │
│  │  We collect your CBP Form 7501 solely to calculate...  │  │
│  │  Documents are encrypted and auto-deleted after 24h.   │  │
│  │  [□] I accept the Privacy Notice and Terms of Use       │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  上傳區域（accept checkbox 勾選後才啟用）                       │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                         │  │
│  │   ⬆  Drag & Drop your CBP Form 7501 here               │  │
│  │      or  [Browse Files]                                 │  │
│  │                                                         │  │
│  │   Accepts: PDF, JPEG, PNG  |  Max: 20 MB               │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  處理狀態列（上傳後顯示）                                       │
│  [●Uploading ──── ○Processing ──── ○Calculating]             │
│  ████████░░░░░  進度條 + 當前步驟說明文字                       │
└──────────────────────────────────────────────────────────────┘
```

**狀態對應 UI：**

| 狀態 | UI 呈現 |
|------|---------|
| `idle` | 上傳區域顯示，拖放提示可見 |
| `privacy_accepted = false` | 上傳區域 disabled（灰色），顯示「請先同意隱私條款」tooltip |
| `uploading` | 進度條動畫，顯示「Uploading…」+ 檔名 + 檔案大小 |
| `processing` | Spinner + 「Analysing document with OCR…」 |
| `review_required` | 自動導向 `/review?job_id={id}` |
| `completed`（無需 review）| 自動觸發計算，導向等待畫面 |
| `failed` | 錯誤 Banner + 對應錯誤文案 + `[Try Again]` 按鈕 |

**錯誤文案對照：**

| 錯誤碼 | 顯示文案（EN）|
|--------|-------------|
| `UNSUPPORTED_FILE_TYPE` | Only PDF, JPEG or PNG files are accepted. |
| `FILE_TOO_LARGE` | File must be under 20 MB. |
| `UNRECOGNISED_DOCUMENT` | We couldn't read this document. Please upload a clear CBP Form 7501. |
| `OCR_TIMEOUT` | Processing timed out. Please try again. |
| `rate_limit` | Too many uploads. Please wait before trying again. |

---

### 4.1.3 Data Review Page（OCR 審查頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/review?job_id={id}` |
| **存取控制** | 公開（session-based，`job_id` 須對應正確 `session_id`）|
| **目的** | 顯示 OCR 提取結果，讓使用者確認或修正低信心欄位 |
| **關鍵業務規則** | BR-010：信心 < 0.80 的欄位以 Amber 標記，須使用者確認 |

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR                                                        │
├──────────────────────────────────────────────────────────────┤
│  步驟指示器 ●──────●──────○                                    │
├──────────────────────────────────────────────────────────────┤
│  說明文字：「Please review the extracted fields below...」     │
│  「Fields highlighted in amber require your attention.」       │
├──────────────────────────────────────────────────────────────┤
│  HEADER FIELDS（報關單基本資訊）                                │
│  ┌────────────────┬────────────────┬────────────────────────┐ │
│  │ Entry Number   │ Summary Date   │  Country of Origin     │ │
│  │ [XXX-1234567-8]│ [2026-02-15]   │  [CN ▼]               │ │
│  │ ✓ 98%          │ ⚠ 72% [AMBER]  │  ✓ 95%                │ │
│  └────────────────┴────────────────┴────────────────────────┘ │
│  ┌────────────────┬──────────────────────────────────────────┐ │
│  │ Entry Type     │  Importer of Record                      │ │
│  │ [01]           │  [ABC Trading Inc.                      ]│ │
│  │ ✓ 91%          │  ✓ 88%                                   │ │
│  └────────────────┴──────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  LINE ITEMS TABLE（HTS 行項目）                                 │
│  ┌──────┬────────────┬──────────────┬──────────┬───────────┐  │
│  │  #   │ HTS Code   │ Entered Value│ Duty Rate│Duty Amount│  │
│  ├──────┼────────────┼──────────────┼──────────┼───────────┤  │
│  │  1   │8471.30.0100│  $12,500.00  │  20.0%   │ $2,500.00 │  │
│  │      │✓ 96%       │  ✓ 94%       │⚠ 65%[AM] │ ✓ 92%    │  │
│  ├──────┼────────────┼──────────────┼──────────┼───────────┤  │
│  │  2   │8471.60.9550│   $8,200.00  │  20.0%   │ $1,640.00 │  │
│  │      │✓ 93%       │  ✓ 90%       │ ✓ 88%    │ ✓ 91%    │  │
│  └──────┴────────────┴──────────────┴──────────┴───────────┘  │
├──────────────────────────────────────────────────────────────┤
│  TOTALS                              Total Duty+Fees: $4,140.00│
├──────────────────────────────────────────────────────────────┤
│  [← Back to Upload]              [Confirm & Calculate →]       │
└──────────────────────────────────────────────────────────────┘
```

**欄位互動規則：**

| 互動 | 行為 |
|------|------|
| 點擊 Amber 欄位 | 進入 inline edit 模式，顯示文字輸入框，原值保留作為 placeholder |
| 修改值後失焦 | 值更新至前端暫存，信心圖示改為「✏ Edited」（藍色）|
| `[Confirm & Calculate]` | 呼叫 `PATCH /api/v1/documents/{job_id}/fields` 儲存修正，再呼叫 `POST /api/v1/documents/{job_id}/calculate`，導向結果等待畫面 |
| 仍有 Amber 欄位未修改 | Button 上方顯示 Warning Banner：「X fields still require review」，但不阻擋提交 |

---

### 4.1.4 Results Page（計算結果頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/results/:calculation_id` |
| **存取控制** | 公開（知道 `calculation_id` URL 即可存取）|
| **目的** | 展示關稅分解、IEEPA 退稅估算、退稅途徑建議 |
| **法規要求** | COMP-005：免責聲明 Banner 強制顯示，不可隱藏 |

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR                                                        │
├──────────────────────────────────────────────────────────────┤
│  步驟指示器 ●──────●──────●                                    │
├──────────────────────────────────────────────────────────────┤
│  REFUND ESTIMATE CALLOUT（最重要的區塊）                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  💰 Estimated IEEPA Refund                             │  │
│  │                                                         │  │
│  │              USD $4,812.50                              │  │
│  │         (Large bold font, green colour)                 │  │
│  │                                                         │  │
│  │  Recommended Pathway:  [PSC]  Post-Summary Correction  │  │
│  │  ✓ Your entry is within 15 days. Act now.              │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  ENTRY SUMMARY                                                 │
│  Entry: XXX-1234567-8  |  Date: 2026-02-15  |  Origin: CN     │
│  Port: 1001            |  Importer: ABC Trading Inc.          │
├──────────────────────────────────────────────────────────────┤
│  DUTY BREAKDOWN TABLE                                          │
│  ┌──────────────────────┬────────────┬────────────┬────────┐  │
│  │ Tariff Component     │    Rate    │  Amount    │ Refund │  │
│  ├──────────────────────┼────────────┼────────────┼────────┤  │
│  │ MFN Base Tariff      │   7.5%     │ $1,575.00  │   —    │  │
│  │ IEEPA Tariff  ★HL   │  20.0%     │ $4,200.00  │   ✓    │  │
│  │ Section 301 (List 3A)│  25.0%     │ $5,250.00  │   —    │  │
│  │ MPF                  │  0.3464%   │   $72.74   │   —    │  │
│  │ HMF                  │  0.125%    │   $26.25   │   —    │  │
│  ├──────────────────────┼────────────┼────────────┼────────┤  │
│  │ TOTAL                │            │$11,123.99  │        │  │
│  └──────────────────────┴────────────┴────────────┴────────┘  │
│  ★HL = IEEPA 行以淡黃色（#FEF3C7）背景高亮顯示                  │
├──────────────────────────────────────────────────────────────┤
│  PATHWAY EXPLANATION（退稅途徑說明）                            │
│  PSC  ●──────○ Protest ○ Ineligible                           │
│  「A Post-Summary Correction can be filed with CBP within     │
│   15 days of the entry summary date. This is the simplest     │
│   and fastest option. Contact a CHB to proceed.」             │
├──────────────────────────────────────────────────────────────┤
│  ACTION BUTTONS                                                │
│  [📄 Download PDF Report]   [📋 Start New Calculation]        │
├──────────────────────────────────────────────────────────────┤
│  LEAD CTA（轉換引導）                                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 「Want to file for a refund? Our customs experts       │  │
│  │   can handle the entire PSC/Protest process.」         │  │
│  │   [Contact Dimerco Customs Advisory →]                 │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  DISCLAIMER BANNER（COMP-005 — 不可隱藏）                      │
│  ⚠ This estimate is for informational purposes only and       │
│    does not constitute legal or tax advice...                  │
└──────────────────────────────────────────────────────────────┘
```

**退稅途徑色彩規範：**

| Pathway | 標籤顏色 | 背景 |
|---------|---------|------|
| `PSC` | 綠色 `#16A34A` | `#DCFCE7` |
| `PROTEST` | 橘色 `#D97706` | `#FEF3C7` |
| `INELIGIBLE` | 紅色 `#DC2626` | `#FEE2E2` |

---

### 4.1.5 Registration / Lead Capture Page（潛客登錄頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/register?calculation_id={id}` |
| **存取控制** | 公開 |
| **目的** | 捕捉潛客聯絡資訊（換取 PDF 報告下載）|
| **觸發點** | 從 Results 頁點擊「Download PDF Report」|

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR                                                        │
├──────────────────────────────────────────────────────────────┤
│  HEADER                                                        │
│  「Get Your Full Refund Report」                               │
│  「Complete the form below to download your personalised      │
│    IEEPA refund analysis report.」                            │
├──────────────────────────────────────────────────────────────┤
│  FORM                                                          │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Full Name *          [                              ]    │ │
│  │ Company Name *       [                              ]    │ │
│  │ Email *              [                              ]    │ │
│  │ Phone                [                              ]    │ │
│  │ Country *            [United States          ▼     ]    │ │
│  │ Preferred Contact *  ○ Email  ○ WhatsApp  ○ WeChat       │ │
│  │                                                          │ │
│  │ [□] I agree to be contacted by Dimerco regarding my      │ │
│  │     customs advisory enquiry.                            │ │
│  └──────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  [⬇ Download PDF Report]  (disabled until form valid + agree) │
└──────────────────────────────────────────────────────────────┘
```

**提交後行為：**
1. 呼叫 `POST /api/v1/leads`（儲存潛客）
2. 呼叫 `POST /api/v1/results/{calculation_id}/export`（產製 PDF）
3. 顯示 Loading Spinner
4. 取得 download token → `GET /api/v1/files/download?token=...` → 瀏覽器下載 PDF
5. 顯示成功訊息：「Your report has been downloaded. Our team will be in touch soon.」

---

### 4.1.6 Bulk Upload Page（批量上傳頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/bulk` |
| **存取控制** | 需登入（Registered User）|
| **目的** | 上傳 CSV / XLSX 批量計算多筆 Entry Summary |

**版面配置（Layout）：**

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR                          [👤 John Doe ▼]  [Logout]   │
├──────────────────────────────────────────────────────────────┤
│  PAGE TITLE：Bulk Refund Calculator                            │
│  副說明：「Upload a CSV or XLSX with multiple entries...」     │
│  [⬇ Download Template]  (CSV 範本下載)                         │
├──────────────────────────────────────────────────────────────┤
│  UPLOAD ZONE                                                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │   ⬆  Drag & Drop CSV or XLSX here                     │  │
│  │      Required columns: entry_number, summary_date,     │  │
│  │      country_of_origin, hts_code, entered_value...     │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  PROGRESS DASHBOARD（上傳後顯示）                               │
│  Total: 48  ✓ Completed: 32  ✗ Failed: 2  ⏳ Processing: 14  │
│  ████████████████████░░░░░░░░░  67%                           │
├──────────────────────────────────────────────────────────────┤
│  RESULTS PREVIEW TABLE（完成後顯示）                            │
│  ┌─────────────┬─────────────┬────────────┬────────────────┐  │
│  │ Entry Number│ Summary Date│ Est. Refund│ Pathway        │  │
│  ├─────────────┼─────────────┼────────────┼────────────────┤  │
│  │XXX-111-1    │ 2026-02-10  │ $2,340.00  │ PSC            │  │
│  │XXX-222-2    │ 2025-10-05  │ $1,120.00  │ INELIGIBLE     │  │
│  └─────────────┴─────────────┴────────────┴────────────────┘  │
│  Total Refundable Across All Entries:  $28,450.00              │
│  [View Full Results →]  [⬇ Export CSV]                        │
└──────────────────────────────────────────────────────────────┘
```

---

### 4.1.7 Bulk Results Page（批量結果頁）

| 屬性 | 內容 |
|------|------|
| **Route** | `/bulk/results/:bulk_job_id` |
| **存取控制** | 需登入（Registered User）|
| **目的** | 完整批量計算結果，含每筆明細與彙整統計 |

**關鍵元素：**
- 頂部 Summary Card：總退稅金額、PSC 件數、Protest 件數、INELIGIBLE 件數
- 可排序、可篩選的結果 Table（依 pathway、refund 金額、日期篩選）
- 每列點擊展開關稅明細（accordion）
- `[Export All as CSV]` 按鈕

---

### 4.1.8 Admin Portal（管理後台）

| 屬性 | 內容 |
|------|------|
| **Route** | `/admin/*` |
| **存取控制** | 需登入（role: admin）|
| **目的** | 稅率管理、潛客列表、使用分析 |

**子頁面：**

| Sub-Route | 頁面 | 核心功能 |
|-----------|------|---------|
| `/admin/rates` | 稅率管理 | HTS 稅率列表（可篩選）、單筆編輯（inline）、CSV 批量匯入 |
| `/admin/leads` | 潛客管理 | 潛客列表（含 CRM 同步狀態）、篩選、CSV 匯出 |
| `/admin/analytics` | 使用分析 | 折線圖（每日計算次數）、圓餅圖（Pathway 分佈）、Top 10 HTS 代碼 |

**稅率管理頁版面：**

```
┌──────────────────────────────────────────────────────────────┐
│  ADMIN NAVBAR                        [Admin: Jane ▼] [Logout] │
│  ─ Rates  ─ Leads  ─ Analytics                                │
├──────────────────────────────────────────────────────────────┤
│  篩選列：[HTS Code 搜尋] [Country ▼] [Tariff Type ▼] [Search] │
│  [+ Add Rate]   [⬆ Import CSV]                                │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────┬────────┬─────────┬──────┬─────────┬────────┐ │
│  │ HTS Code   │Country │ Type    │ Rate │Eff. From│Actions │ │
│  ├────────────┼────────┼─────────┼──────┼─────────┼────────┤ │
│  │8471.30.0100│  CN    │ IEEPA   │20.00%│2025-04-02│[Edit] │ │
│  │8471.30.0100│  CN    │ S301    │25.00%│2018-09-24│[Edit] │ │
│  └────────────┴────────┴─────────┴──────┴─────────┴────────┘ │
│  Pagination：< 1 2 3 ... 48 >                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Section 4.2 — Input Fields（輸入欄位定義）

### 4.2.1 文件上傳欄位

| 欄位 ID | 欄位名稱 | 類型 | 必填 | 驗證規則 | 前端錯誤訊息 |
|---------|---------|------|------|---------|------------|
| `file` | CBP Form 7501 File | File Input | ✓ | MIME: `application/pdf` \| `image/jpeg` \| `image/png`；大小 ≤ 20MB | `Only PDF, JPEG, PNG accepted` |
| `privacy_accepted` | 隱私聲明同意 | Checkbox | ✓ | 必須為 `true` 才能提交 | `You must accept the Privacy Notice to continue` |

---

### 4.2.2 OCR 審查可編輯欄位（Form 7501 Fields）

以下欄位由 OCR 自動提取，使用者可於 `/review` 頁修正：

| 欄位 ID（内部 Key）| Box # | 欄位名稱 | 類型 | 驗證規則 | 格式範例 |
|---------------------|-------|---------|------|---------|---------|
| `entry_number` | Box 1 | Entry Number | Text | `^[A-Z0-9]{3}-[0-9]{7}-[0-9]$` | `ABC-1234567-8` |
| `entry_type` | Box 2 | Entry Type | Text | `^[0-9]{2}$` | `01` |
| `summary_date` | Box 3 | Summary Date | Date | ISO 8601；近 5 年內 | `2026-02-15` |
| `port_code` | Box 5 | Port of Entry | Text | `^[0-9]{4}$` | `1001` |
| `importer_name` | Box 11 | Importer of Record | Text | Non-empty | `ABC Trading Inc.` |
| `country_of_origin` | Box 14 | Country of Origin | Select | ISO 3166-1 alpha-2；2 字元 | `CN` |
| `hts_code[]` | Box 29 | HTS Number（每行）| Text（array）| `^[0-9]{10}$` | `8471300100` |
| `entered_value[]` | Box 31 | Entered Value（每行）| Number（array）| 正小數，USD | `12500.00` |
| `duty_rate[]` | Box 33 | Duty Rate（每行）| Text（array）| `^[0-9]+(\.[0-9]+)?%$` | `20.0%` |
| `duty_amount[]` | Box 34 | Duty Amount（每行）| Number（array）| 正小數，USD | `2500.00` |
| `total_duty_fees` | Box 44 | Total Duty + Fees | Number | 正小數，須與行項目加總交叉驗證 | `4140.00` |
| `mode_of_transport` | — | Mode of Transport | Select | `vessel` \| `air` \| `other` | `vessel` |

**信心分數視覺化規範：**

| 信心範圍 | 樣式 | 圖示 | 可編輯 |
|----------|------|------|--------|
| ≥ 0.90 | 正常（無邊框）| `✓` 綠色 | 可點擊編輯 |
| 0.80 ~ 0.89 | 正常 | `✓` 灰色 | 可點擊編輯 |
| < 0.80（`review_required`）| Amber 邊框 `border-amber-500` | `⚠` 橘色 | **預設展開 inline edit** |
| 使用者已修正 | 藍色邊框 `border-blue-500` | `✏` 藍色 | 可再次點擊修改 |

---

### 4.2.3 Lead Capture 表單欄位（/register）

| 欄位 ID | 欄位名稱 | 類型 | 必填 | 驗證規則 | 加密儲存 |
|---------|---------|------|------|---------|---------|
| `full_name` | Full Name | Text | ✓ | 非空白，最長 200 字元 | ✓ AES-256-GCM |
| `company_name` | Company Name | Text | ✓ | 非空白，最長 200 字元 | — |
| `email` | Email Address | Email | ✓ | RFC 5322 Email 格式 | ✓ AES-256-GCM |
| `phone` | Phone Number | Tel | — | E.164 格式或留空 | ✓ AES-256-GCM |
| `country` | Country | Select | ✓ | ISO 3166-1 alpha-2；下拉選單 | — |
| `preferred_contact` | Preferred Contact | Radio | ✓ | `email` \| `whatsapp` \| `wechat` | — |
| `contact_consent` | 聯絡同意聲明 | Checkbox | ✓ | 必須為 `true` | — |
| `calculation_id` | （hidden）| Hidden | ✓ | UUID v4，來自 URL param | — |

**Zod Schema（前端驗證）：**

```typescript
const LeadSchema = z.object({
  full_name:         z.string().min(1).max(200),
  company_name:      z.string().min(1).max(200),
  email:             z.string().email(),
  phone:             z.string().regex(/^\+?[1-9]\d{1,14}$/).optional().or(z.literal("")),
  country:           z.string().length(2),
  preferred_contact: z.enum(["email", "whatsapp", "wechat"]),
  contact_consent:   z.literal(true, { errorMap: () => ({ message: "Consent required" }) }),
  calculation_id:    z.string().uuid(),
});
```

---

### 4.2.4 使用者註冊表單欄位（/auth/register）

| 欄位 ID | 欄位名稱 | 類型 | 必填 | 驗證規則 |
|---------|---------|------|------|---------|
| `email` | Email | Email | ✓ | RFC 5322 格式；唯一性由後端驗證 |
| `password` | Password | Password | ✓ | 最短 8 字元，含大寫/小寫/數字各至少一個 |
| `password_confirm` | Confirm Password | Password | ✓ | 須與 `password` 相同 |
| `full_name` | Full Name | Text | ✓ | 非空白，最長 200 字元 |
| `company_name` | Company Name | Text | — | 最長 200 字元 |

**密碼強度指示器：**  
即時顯示：Weak（紅）→ Fair（橘）→ Strong（綠），依長度、大小寫、數字計算。

---

### 4.2.5 登入表單欄位（/auth/login）

| 欄位 ID | 欄位名稱 | 類型 | 必填 | 驗證規則 |
|---------|---------|------|------|---------|
| `email` | Email | Email | ✓ | RFC 5322 格式 |
| `password` | Password | Password | ✓ | 非空白 |

> 登入失敗一律顯示「Email or password is incorrect」，不區分帳號是否存在（防帳號枚舉，參考 Security_Spec.md 7.1.3）。

---

### 4.2.6 批量上傳 CSV / XLSX 欄位規格

| 欄位名稱（CSV Header）| 說明 | 必填 | 格式 |
|----------------------|------|------|------|
| `entry_number` | 報關單號 | ✓ | `XXX-1234567-8` |
| `summary_date` | 申報日期 | ✓ | `YYYY-MM-DD` |
| `country_of_origin` | 原產地 | ✓ | ISO 3166-1 alpha-2（e.g. `CN`）|
| `importer_name` | 進口商名稱 | ✓ | 任意字串 |
| `port_code` | 口岸代碼 | — | 4 位數字 |
| `mode_of_transport` | 運輸方式 | — | `vessel` \| `air`（預設 `vessel`）|
| `hts_code_{n}` | HTS 代碼（第 n 行）| ✓（至少 1 行）| 10 位數字 |
| `entered_value_{n}` | 申報值（第 n 行）| ✓ | 正小數 USD |
| `duty_rate_{n}` | 關稅率（第 n 行）| — | `20.0%` |
| `duty_amount_{n}` | 關稅金額（第 n 行）| — | 正小數 USD |

> `{n}` 從 `1` 開始遞增，支援最多 20 個 HTS 行項目。`[Download Template]` 按鈕提供預填範例。

---

### 4.2.7 管理員稅率新增 / 編輯表單

| 欄位 ID | 欄位名稱 | 類型 | 必填 | 驗證規則 |
|---------|---------|------|------|---------|
| `hts_code` | HTS Code | Text | ✓ | `^[0-9]{10}$` |
| `country_code` | Country Code | Select | ✓ | ISO 3166-1 alpha-2 |
| `tariff_type` | Tariff Type | Select | ✓ | `MFN` \| `IEEPA` \| `S301` \| `S232` |
| `rate_pct` | Rate (%) | Number | ✓ | 正小數，`> 0`，`≤ 999.9999` |
| `effective_from` | Effective From | Date | ✓ | ISO 8601，不可為未來日期的修改（需 change request）|
| `effective_to` | Effective To | Date | — | 留空表示「目前有效」；若填入須 > `effective_from` |
| `source_ref` | Federal Register Ref | Text | — | 聯邦公報引用，如 `89 FR 12345` |

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
