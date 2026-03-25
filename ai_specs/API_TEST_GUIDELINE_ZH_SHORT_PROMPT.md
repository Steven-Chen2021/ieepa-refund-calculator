# AI 產生 API Test Case 超短 Prompt

```text
請直接分析完整 Source Code，自動找出所有相關 API / 程式介面，並產出完整 API Test Cases。

必須涵蓋：
- 功能性測試
- 正常與異常輸入
- 必填 / 選填欄位驗證
- null / 空字串 / 全空白情境
- 最小值 / 最大值 / 邊界值
- 極小值 / 極大值
- 資料型別檢查
- 資料格式 / 型態檢查
- enum 驗證
- 欄位相依性驗證
- 重複請求 / 冪等性驗證
- Authentication / Authorization 驗證（若適用）
- Response Contract 驗證
- Data Check 與 Side Effect Check

請先根據 Source Code 推導：
- API / Function 清單
- 路徑 / 方法 / 功能目的
- request fields / input parameters
- 必填 / 選填
- 型別、格式、長度、最小值、最大值、enum、nullable
- 商業規則、前置條件、狀態轉換、錯誤處理
- 成功 / 失敗回應
- 狀態碼、錯誤碼、response schema
- DB / event / queue / log / downstream call 等副作用

請輸出：
- 測試範圍
- 假設
- Source Code 證據摘要
- 推導出的 API / Function 清單
- 欄位盤點
- 分類測試案例
- 完整測試案例總表
- 最低必要案例檢查表
- 最終 Merge Readiness 結論

規則：
- 先以 Source Code 為準，無法確認時才做合理假設，且必須明確標示
- 每個推導出的規則盡量附上來源檔案、function、schema、validator 或 route 證據
- 若必要案例缺漏、未執行、失敗、或定義不清，結論一律為 "Merge Blocked"
- 只有在必要測試案例完整、可執行、且結果應全部通過時，才可判定為 "Merge Allowed"
```
