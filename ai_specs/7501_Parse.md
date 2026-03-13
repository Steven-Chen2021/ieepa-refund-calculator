# 技術需求規格：CBP 7501 Form OCR 數據提取邏輯

## 1. 任務目標 (Project Objective)
從上傳的 CBP 7501 PDF 文件中精確提取報關核心數據，並計算每個欄位的信心評分 (Confidence Score)。

## 2. 欄位提取邏輯 (Extraction Logic)

### A. 單一值欄位 (Header Fields)
| 序號 | 欄位名稱 (Field Name) | 參考框號 (Box No.) | 提取邏輯定義 (Logic) | [cite_start]範例數據 (Example) [cite: 12-15, 27, 32, 79] |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 報關行代碼/報單號碼 | Box 1 | 搜尋 "1. Filer Code/Entry No."，讀取下方兩行或對應網格 | MYK / 2810374-2 |
| 2 | 報單類型 (Entry Type) | Box 2 | 搜尋 "2. Entry Type"，讀取其數值與描述 | 01 (ABI/A) |
| 3 | 進口日期 (Import Date) | Box 11 | 搜尋 "11. Import Date"，格式化為 YYYY-MM-DD | 2026-01-28 |
| 4 | 提單號碼 (B/L No.) | Box 12 | 搜尋 "12. B/L or AWB No."，抓取對應字符 | HLCUSHA260121460 |
| 5 | 總關稅 (Duty) | Box 37 | 搜尋 "37. Duty" 下方的數值，移除 "$" 符號 | 17625.60 |

### B. 表格值欄位 (Line Item Table) - 涉及 Box 29 & 33
* **觸發條件**：當 Box 27 (Line No.) 出現新編號時開始紀錄。
* [cite_start]**跨頁處理**：需掃描 Continuation Sheets 並依據 Line No. 整合數據 。

| Line No. | 29. HTSUS No. (含附加稅則) | 33. HTSUS Rate / AD/CVD Rate | 邏輯說明 |
| :--- | :--- | :--- | :--- |
| 001 | 8508.19.0000 | 25% | [cite_start]主稅則與稅率  |
| 001 | 9903.88.03 | 25% | 附加稅則 (Section 301) |
| 001 | 9903.01.24 | 10% | **IEEPA 稅則 (退稅目標)** |
| 001 | 9903.01.25 | 10% | **IEEPA 稅則 (退稅目標)** |

## 3. UI 呈現與可靠度規範 (UI & Confidence Rules)
1. **可靠度呈現 (Confidence Metric)**: 
   - 每個欄位旁需顯示 `%` (由 OCR API 返回的信心水準)。
   - `Confidence < 85%`：該欄位背景顯示為黃色，提醒檢核。
   - `Confidence < 50%`：欄位標記為「讀取失敗」，背景顯示為紅色。
2. **表格呈現**: Box 29 與 33 的數據必須以 Grid Table 形式展現，同一 Line No. 的所有附加稅則需合併在同一群組內。

## 4. 異常校驗 (Validation Rules)
- [cite_start]**日期校驗**：Box 11 (Import Date) 不得晚於 Box 3 (Summary Date) [cite: 15, 27]。
- **金額校驗**：所有項目的 Duty 加總應等於 Box 37 的總金額。