# Project Context
**Document Reference:** DMX-TRS-IEEPA-2026-001  
**Based On BRS:** DMX-BRS-IEEPA-2026-001 v1.0  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Section 1.2 — Problem Statement

### 背景 (Background)

自 2025 年起，美國依據《國際緊急經濟權力法》（IEEPA）對中國原產地貨物加徵額外關稅。大量 U.S. 進口商因此被額外課徵 IEEPA 關稅，但多數業者並不了解：
- 已繳納的 IEEPA 關稅有機會申請退稅。
- 退稅途徑（Post-Summary Correction / Protest）有嚴格的時效限制。
- 正確計算退稅金額需要複雜的 HTS 稅率分解邏輯及 CBP 規則知識。

### 痛點 (Pain Points)

| # | 痛點 | 影響對象 |
|---|------|----------|
| P-01 | 進口商不知道自己可能符合 IEEPA 退稅資格 | 進口商 |
| P-02 | 計算各關稅組成（MFN / IEEPA / S301 / S232 / MPF / HMF）極為繁瑣 | 進口商、報關行 |
| P-03 | 退稅時效（PSC 15 天 / Protest 180 天）不熟悉，錯過申請時機 | 進口商 |
| P-04 | CBP Form 7501 欄位解讀複雜，需要專業報關知識 | 進口商 |
| P-05 | Dimerco 業務拓展缺乏有效的數位潛客捕捉機制 | Dimerco 業務團隊 |

### 解決方案概述 (Solution Overview)

**IEEPA Tariff Refund Calculator** — 一個公開可存取、行動響應式的 Web Portal，允許 U.S. 進口商及物流專業人員：

1. 上傳 CBP Form 7501（Entry Summary）PDF 或圖片。
2. 取得各稅項的逐項拆解（MFN、IEEPA、Section 301、Section 232、MPF、HMF）。
3. 獲得估算的 IEEPA 退稅金額。
4. 獲得推薦退稅途徑（PSC 或 Protest）及理由說明。
5. 下載 PDF 報告（需留下聯絡資訊，為 Dimerco 關務顧問服務提供潛在客戶）。

該系統同時為 Dimerco 提供後台管理功能，包含稅率維護、潛客管理及使用統計。

### 系統邊界 (System Boundaries)

**範圍內 (In Scope):**
- CBP Form 7501 OCR 解析與欄位提取
- 關稅組成計算引擎（MFN / IEEPA / S301 / S232 / MPF / HMF）
- 退稅途徑判斷（PSC / PROTEST / INELIGIBLE）
- PDF 報告產製
- 潛客捕捉與 CRM 同步
- 管理後台（稅率管理、潛客匯出、使用分析）
- 批量上傳功能（已註冊使用者）

**範圍外 (Out of Scope):**
- 實際向 CBP 提交 PSC 或 Protest 文件
- 法律建議或稅務建議（系統僅提供估算，附免責聲明）
- 非中國原產地的 IEEPA 計算（IEEPA 關稅目前僅適用於 CN）

---

## Section 1.3 — Users

### 使用者角色定義 (User Role Definitions)

#### 1.3.1 Guest User（訪客使用者）

| 屬性 | 說明 |
|------|------|
| **身份** | 未登入的一般訪客 |
| **代表族群** | U.S. 進口商、採購主管、物流協調員 |
| **主要目標** | 快速評估某批進口貨物的 IEEPA 退稅潛力 |
| **技術能力** | 熟悉 CBP Form 7501，但不一定具備關稅計算專業 |
| **存取權限** | 上傳 Form 7501、查看計算結果、下載 PDF（需填寫聯絡資訊）|
| **語言需求** | 英文或簡體中文（zh-CN / en 切換）|

**使用情境（Use Case）：**
> 一位來自上海的採購主管負責管理公司在美國的進口業務。他/她收到 4 月份的 CBP 7501，懷疑其中有 IEEPA 附加關稅，想知道是否有退稅機會，但不想立刻聯繫報關行。他/她透過 Dimerco 網站找到此工具，上傳 PDF，幾分鐘後得到退稅估算及 PSC 建議。

---

#### 1.3.2 Registered User（已登入使用者）

| 屬性 | 說明 |
|------|------|
| **身份** | 已完成電子郵件驗證的帳戶持有人 |
| **代表族群** | 物流業者、報關行（CHB）、進口商關務部門 |
| **主要目標** | 批量處理多筆進口報關單，取得彙整退稅報告 |
| **技術能力** | 具備一定 HTS 分類及 CBP 規則知識 |
| **存取權限** | Guest 的所有權限 + 批量 CSV/XLSX 上傳、歷史計算紀錄查詢 |

**使用情境（Use Case）：**
> 一位 CHB（持牌報關行）每月處理數十筆中國原產地進口報關單。他/她匯出一份包含所有 Entry Summary 資料的 XLSX，上傳至批量計算功能，一次取得所有客戶的退稅估算，並協助客戶決定是否提交 Protest。

---

#### 1.3.3 Admin User（管理員使用者）

| 屬性 | 說明 |
|------|------|
| **身份** | Dimerco 內部授權人員（IT 或關務作業團隊）|
| **代表族群** | Dimerco 關務作業主管、CIO Office |
| **主要目標** | 維護 HTS 稅率資料庫、查看潛客名單、監控系統使用狀況 |
| **技術能力** | 熟悉 HTS 稅率更新流程及美國關稅政策 |
| **存取權限** | 稅率 CRUD、潛客列表/匯出、使用分析儀表板 |
| **驗證要求** | 需具備 `role: admin` 的有效 JWT |

**使用情境（Use Case）：**
> 當 IEEPA 稅率調整時（如聯邦公報發布新稅率），關務作業主管登入管理後台，透過 CSV 批量匯入新稅率，並驗證系統計算結果是否正確反映新費率。

---

#### 1.3.4 使用者旅程摘要 (User Journey Summary)

```
[Guest / Registered User]
Landing Page
    └─> /calculate  →  Upload Form 7501 (PDF/Image)
            └─> /review     →  Confirm / Correct OCR Fields
                    └─> /results/:id  →  View Duty Breakdown + Refund Estimate
                                └─> /register  →  (Lead Capture) Download PDF Report
                                └─> /bulk      →  (Registered) Bulk Upload

[Admin]
/admin/*
    ├─> Rate Management   (GET / PUT / POST rates)
    ├─> Lead Management   (GET leads, CSV export)
    └─> Analytics         (Usage statistics dashboard)
```

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
