

# 🌐 AI_DEVELOPMENT_PROTOCOL.md

**文件編號：** DMX-IT-GEN-2026-001

**版本：** v1.0 (通用版)

**核心宗旨：** 規範 AI Agent 與 Dimerco 開發者之協作流，確保代碼品質、資安稽核與營運韌性。

---

## 1. 啟動階段：上下文識別 (Context Initialization)

在執行任何修改前，AI Agent 必須：

* **讀取規格：** 自動檢索專案目錄下的 `Business_Rules.md`、`README.md` 或 `Spec.md`。
* **建立分支：** 嚴禁在 `main` 研發。必須執行 `git checkout -b feature/<任務類別>-<簡短描述>`。

## 2. 開發階段：防錯與合規 (Safe Development)

* **最小改動原則：** 僅針對需求範圍進行修改，避免變更無關邏輯。
* **安全編碼：** 必須遵循專案定義的安全性要求（如 PII 加密、信心度閾值設定等）。
* **稽核紀錄：** 確保所有關鍵計算或資料異動均有 Audit Trail 實作。

## 3. 驗證階段：品質保證 (Quality Assurance)

* **執行測試：** 提交前必須執行專案內定義的所有單元測試或整合測試。
* **回報結果：** AI Agent 應主動列出測試通過筆數及是否有任何已知的邊界案例未處理。

## 4. 交付階段：提交與推送 (Commit & Push)

* **暫存變更：** `git add .`
* **標準提交：** `git commit -m "<類型>: <描述> per <文件編號>"` (類型可選: feat, fix, docs, test, refactor)。
* **詳細紀錄：** 提交訊息必須包含修改的模組清單及具體變更邏輯，並註記 `Co-authored-by`。
* **上傳遠端：** `git push origin <分支名稱>`。

## 5. 完成階段：發起 Pull Request (PR)

AI Agent 完成 Push 後，**必須自動生成**以下格式的 PR 邀請訊息：

> 「✅ **開發已完成**
> * **分支路徑：** `feature/<名稱>`
> * **業務目標：** (依據 Business_Rules.md 摘要目標)
> * **測試狀態：** 通過 [N] 個測試案例
> * **PR 連結：** [請點擊此處建立 Pull Request 並指派 Reviewer]」
> 
> 
