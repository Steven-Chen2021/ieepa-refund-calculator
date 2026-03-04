# Test Cases
**Document Reference:** DMX-TRS-IEEPA-2026-001 (Local Deployment Edition)  
**Based On:** Business_Rules.md · API_Endpoint.md · UI_Spec.md · Security_Spec.md · Glossary.md  
**Owner:** Office of the CIO, Dimerco Express Group  
**Version:** 1.0 | March 2026 | Internal — Confidential

---

## Section 8.1 — Test Cases

### 測試框架與工具

| 測試類型 | 工具 | 覆蓋率目標 | 執行時機 |
|----------|------|-----------|---------|
| Backend Unit Tests | `pytest` + `coverage.py` | ≥ 80% line coverage | PR + 每次 commit |
| API Integration Tests | `pytest` + `httpx` (async) | 100% endpoints | PR |
| Calculation Engine Tests | `pytest` + fixture entries | 100% calculation paths | PR |
| Frontend Unit Tests | `Vitest` + React Testing Library | ≥ 75% line coverage | PR |
| E2E Tests | `Playwright` | 所有 Critical User Journey | Staging 部署後 |
| Performance Tests | `k6` or `Locust` | 500 concurrent users | Staging 部署後 |
| Security Tests | `bandit` + `pip-audit` + 第三方滲透測試 | OWASP Top 10 | 上線前 |

---

## 8.1.1 Calculation Engine Tests（計算引擎測試）

> 所有計算測試使用 pytest fixture，以 `TEST_TARIFF_FIXTURE` 資料庫（種子資料集）執行，不影響 Production 稅率。

### TC-CALC-001：MFN 基本稅計算（BR-002）

**測試目標：** `mfn_tariff = entered_value × mfn_rate`

| Case | hts_code | country | entered_value | mfn_rate | expected_mfn | 說明 |
|------|----------|---------|--------------|----------|-------------|------|
| A | `8471300100` | CN | $12,500.00 | 7.5% | $937.50 | 標準計算 |
| B | `6110200010` | CN | $5,000.00 | 12.0% | $600.00 | 不同 HTS 稅率 |
| C | `8471300100` | TW | $12,500.00 | 7.5% | $937.50 | 非 CN 亦有 MFN |
| D | `9999999999` | CN | $1,000.00 | 0% | $0.00 | 零稅率 HTS |

```python
# pytest 範例
@pytest.mark.parametrize("hts,country,value,rate,expected", [
    ("8471300100", "CN", 12500.00, 0.075, 937.50),
    ("6110200010", "CN", 5000.00,  0.120, 600.00),
])
async def test_mfn_calculation(hts, country, value, rate, expected, db_session):
    result = await calculate_mfn(hts_code=hts, country_code=country,
                                  entered_value=value, summary_date=date(2026, 2, 15),
                                  db=db_session)
    assert result.amount == pytest.approx(expected, rel=1e-4)
```

---

### TC-CALC-002：IEEPA 關稅計算（BR-001）

**測試目標：** IEEPA 僅適用 CN 原產地；非 CN 回傳 $0

| Case | country | entered_value | ieepa_rate | expected_ieepa | 說明 |
|------|---------|--------------|------------|---------------|------|
| A | CN | $12,500.00 | 20.0% | **$2,500.00** | 標準 CN 計算 |
| B | TW | $12,500.00 | 20.0% | **$0.00** | 非 CN → $0（BR-001 例外）|
| C | VN | $8,000.00 | 20.0% | **$0.00** | 非 CN → $0 |
| D | CN | $12,500.00 | 20.0% | $0.00 | summary_date 在 IEEPA 生效前 → $0 |
| E | CN | $0.01 | 20.0% | $0.00 | 最小值邊界（0.0002 → 四捨五入 $0.00）|

```python
async def test_ieepa_non_cn_returns_zero(db_session):
    result = await calculate_ieepa(hts_code="8471300100", country_code="TW",
                                    entered_value=12500.00,
                                    summary_date=date(2026, 2, 15), db=db_session)
    assert result.amount == 0.00
    assert result.tariff_type == "IEEPA"
```

---

### TC-CALC-003：Section 301 關稅計算（BR-003）

**測試目標：** 依 HTS 代碼正確識別 List 分類並套用稅率

| Case | hts_code | expected_list | expected_rate | expected_s301 |
|------|----------|-------------|--------------|--------------|
| A | `8471300100` | List 3A | 25.0% | $3,125.00（$12,500×25%）|
| B | `6110200010` | List 4A | 7.5% | $375.00（$5,000×7.5%）|
| C | `0101210000` | None | 0% | $0.00（未在任何清單中）|

---

### TC-CALC-004：Section 232 關稅計算（BR-004）

**測試目標：** 鋼鐵/鋁 HTS 代碼標記並計算，其他回傳 false

| Case | hts_code | expected_s232_applicable | expected_amount |
|------|----------|------------------------|----------------|
| A | `7208390000`（鋼鐵）| `true` | $12,500×25% = $3,125.00 |
| B | `7601100000`（鋁）| `true` | $8,000×10% = $800.00 |
| C | `8471300100`（電腦）| `false` | $0.00 |

---

### TC-CALC-005：MPF 計算（BR-005）— 邊界值測試

**測試目標：** 正確套用下限 $32.71、上限 $634.62，費率 0.3464%

| Case | total_entered_value | raw_mpf | expected_mpf | 說明 |
|------|-------------------|---------|-------------|------|
| A | $9,444.00 | $32.70 | **$32.71** | 低於下限 → 取下限 |
| B | $9,445.00 | $32.70 | **$32.71** | 恰好低於下限 |
| C | $9,446.00 | $32.71 | **$32.71** | 恰好等於下限 |
| D | $50,000.00 | $173.20 | **$173.20** | 正常範圍 |
| E | $183,215.00 | $634.62 | **$634.62** | 恰好等於上限 |
| F | $183,216.00 | $634.62 | **$634.62** | 超過上限 → 取上限 |
| G | $200,000.00 | $692.80 | **$634.62** | 超過上限 → 取上限 |

```python
@pytest.mark.parametrize("entered_value,expected_mpf", [
    (9444.00,   32.71),   # 低於下限
    (9446.00,   32.71),   # 恰好下限
    (50000.00,  173.20),  # 正常範圍
    (183215.00, 634.62),  # 恰好上限
    (200000.00, 634.62),  # 超過上限
])
def test_mpf_boundary_values(entered_value, expected_mpf):
    assert calculate_mpf(entered_value) == pytest.approx(expected_mpf, rel=1e-4)
```

---

### TC-CALC-006：HMF 計算（BR-006）

**測試目標：** 海運計算 0.125%；空運回傳 $0

| Case | mode_of_transport | total_entered_value | expected_hmf |
|------|-----------------|-------------------|-------------|
| A | `vessel` | $20,000.00 | **$25.00** |
| B | `air` | $20,000.00 | **$0.00** |
| C | `other` | $20,000.00 | **$0.00** |

---

### TC-CALC-007：退稅途徑判斷（BR-007）— 邊界值測試

**測試目標：** 以 `summary_date` 距今天數正確判斷 PSC / PROTEST / INELIGIBLE

| Case | days_elapsed | expected_pathway | 邊界說明 |
|------|-------------|-----------------|---------|
| A | 0 | **PSC** | 同日申報 |
| B | 14 | **PSC** | PSC 期限內 |
| C | **15** | **PSC** | **邊界值：第 15 天仍為 PSC** |
| D | **16** | **PROTEST** | **邊界值：第 16 天轉為 PROTEST** |
| E | 100 | **PROTEST** | Protest 期限內 |
| F | **180** | **PROTEST** | **邊界值：第 180 天仍為 PROTEST** |
| G | **181** | **INELIGIBLE** | **邊界值：第 181 天超過時效** |
| H | 365 | **INELIGIBLE** | 遠超時效 |

```python
from datetime import date, timedelta

@pytest.mark.parametrize("days,expected", [
    (0,   "PSC"),
    (15,  "PSC"),
    (16,  "PROTEST"),
    (180, "PROTEST"),
    (181, "INELIGIBLE"),
    (365, "INELIGIBLE"),
])
def test_refund_pathway_boundaries(days, expected):
    summary_date = date.today() - timedelta(days=days)
    assert determine_refund_pathway(summary_date) == expected
```

---

### TC-CALC-008：退稅金額加總（BR-008）

**測試目標：** `estimated_refund = Σ ieepa_tariff`（僅 IEEPA，不含其他稅項）

| Case | 行項目 | IEEPA 合計 | 非 IEEPA 合計 | expected_refund |
|------|-------|-----------|-------------|----------------|
| A | 2 個 CN HTS | $2,500 + $1,640 | $5,000（S301）| **$4,140.00** |
| B | 1 個 CN + 1 個 TW | $2,500 + $0 | — | **$2,500.00** |
| C | 全部非 CN | $0 + $0 | — | **$0.00** |

---

### TC-CALC-009：稅率查詢邏輯（BR-009）

**測試目標：** 以 `summary_date` 查詢正確的有效稅率版本

| Case | summary_date | tariff_type | 資料庫現有記錄 | expected_rate |
|------|-------------|-------------|-------------|--------------|
| A | 2026-02-15 | IEEPA | `effective_from=2025-04-02, effective_to=NULL` | 20.0% |
| B | 2025-03-01 | IEEPA | 生效前 → 無符合記錄 | 0%（無稅率）|
| C | 2026-01-01 | IEEPA | `effective_from=2025-04-02, effective_to=2025-12-31` → 另一筆 `2026-01-01` | 新稅率 |

---

### TC-CALC-010：計算稽核軌跡不可刪除（BR-011）

```python
async def test_calculation_audit_immutable(db_session):
    # 執行計算
    calc_id = await run_calculation(job_id=fixture_job_id, db=db_session)
    # 確認 audit 記錄存在
    audit = await db_session.get(CalculationAudit, calc_id)
    assert audit is not None
    assert audit.input_snapshot is not None
    assert audit.rate_lookups is not None
    # 確認無法刪除（DB 層觸發器或 Row-Level Security）
    with pytest.raises(Exception, match="audit.*immutable|delete.*prohibited"):
        await db_session.delete(audit)
        await db_session.commit()
```

---

### TC-CALC-011：完整計算整合（CHB 驗證案例）

**測試目標：** 以真實報關單驗證，系統計算結果與持牌 CHB 手工計算差異 ≤ 2%

| 案例編號 | entry_number | summary_date | country | 總申報值 | CHB 計算 IEEPA | 系統計算 IEEPA | 差異 |
|---------|-------------|-------------|---------|---------|--------------|--------------|------|
| CHB-001 | `ABC-1111111-1` | 2026-01-15 | CN | $45,000 | $9,000.00 | — | ≤ 2% |
| CHB-002 | `DEF-2222222-2` | 2026-02-01 | CN | $12,800 | $2,560.00 | — | ≤ 2% |
| CHB-003 | `GHI-3333333-3` | 2025-11-01 | TW | $30,000 | $0.00 | — | $0 |

> 測試資料集由持牌 CHB 驗證，實際數值於 UAT 階段填入。

---

## 8.1.2 OCR & Document Parsing Tests（OCR 解析測試）

### TC-OCR-001：Form 7501 欄位提取精度

**測試目標：** 50 份真實文件測試集，欄位平均準確率 ≥ 95%

```python
@pytest.mark.slow
async def test_ocr_accuracy_corpus(ocr_engine, test_corpus_dir):
    """
    測試語料庫：50 份已標注的真實 Form 7501 PDF
    每份文件有對應的 ground_truth.json（手工標注正確值）
    """
    results = []
    for doc_path in Path(test_corpus_dir).glob("*.pdf"):
        ground_truth = json.loads((doc_path.with_suffix(".json")).read_text())
        extracted = await ocr_engine.extract(doc_path)
        for field_name, expected_value in ground_truth.items():
            extracted_value = extracted.get(field_name, {}).get("value")
            results.append(normalize(extracted_value) == normalize(expected_value))
    accuracy = sum(results) / len(results)
    assert accuracy >= 0.95, f"OCR accuracy {accuracy:.2%} < 95%"
```

---

### TC-OCR-002：低信心欄位標記（BR-010）

| Case | 場景 | ocr_confidence | expected_review_required |
|------|------|---------------|------------------------|
| A | 清晰掃描件 | 0.95 | `false` |
| B | 輕微模糊 | 0.79 | **`true`** |
| C | 恰好邊界 | 0.80 | `false`（≥ 0.80 不標記）|
| D | 嚴重模糊 | 0.50 | **`true`** |

---

### TC-OCR-003：整份文件辨識失敗

| Case | 場景 | overall_confidence | expected_result |
|------|------|-------------------|----------------|
| A | 非 Form 7501（隨機 PDF）| 0.22 | `error: UNRECOGNISED_DOCUMENT` |
| B | 空白頁 | 0.00 | `error: UNRECOGNISED_DOCUMENT` |
| C | 低品質但可辨識 | 0.51 | 正常解析（僅部分欄位標記 review）|

---

### TC-OCR-004：多頁文件（最多 8 頁）

```python
async def test_multipage_document(ocr_engine, sample_8page_7501):
    result = await ocr_engine.extract(sample_8page_7501)
    # 確認所有頁面的 line_items 均被提取
    assert len(result["line_items"]) >= 10  # 8 頁應有多個行項目
    assert result["total_duty_fees"]["value"] is not None
```

---

### TC-OCR-005：OCR Fallback 觸發

```python
async def test_ocr_fallback_to_tesseract(monkeypatch, sample_7501):
    # 模擬 Google Document AI 拋出 ServiceUnavailable
    monkeypatch.setattr("app.ocr.google_dai.extract", AsyncMock(side_effect=Exception("503")))
    result = await process_document(job_id="test-job", file_path=sample_7501)
    assert result["ocr_provider"] == "tesseract_fallback"
    assert result["status"] in ["completed", "review_required"]
```

---

### TC-OCR-006：檔案格式驗證

| Case | 檔案 | MIME | Magic Bytes | expected_result |
|------|------|------|------------|----------------|
| A | `form7501.pdf` | `application/pdf` | `%PDF` | `202 Accepted` |
| B | `photo.jpg` | `image/jpeg` | `FFD8FF` | `202 Accepted` |
| C | `scan.png` | `image/png` | `89504E47` | `202 Accepted` |
| D | `virus.exe` 改名 `fake.pdf` | `application/octet-stream` | `MZ...` | `415 UNSUPPORTED_FILE_TYPE` |
| E | `doc.docx` | `application/vnd.openxmlformats` | `PK...` | `415 UNSUPPORTED_FILE_TYPE` |
| F | 25MB PDF | `application/pdf` | `%PDF` | `413 FILE_TOO_LARGE` |

---

## 8.1.3 API Integration Tests（API 整合測試）

> 所有 API 測試使用 `httpx.AsyncClient` 連接測試用 FastAPI app（`TestClient`），搭配測試資料庫（PostgreSQL with `--no-header` schema in transaction rollback）。

### TC-API-001：文件上傳端點

```python
async def test_upload_success(client: AsyncClient, sample_pdf, db):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("form7501.pdf", sample_pdf, "application/pdf")},
        data={"privacy_accepted": "true"},
        headers={"X-Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "queued"
    assert "job_id" in body["data"]
    # Cookie 應被設定
    assert "session_id" in response.cookies

async def test_upload_without_privacy_consent(client, sample_pdf):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("f.pdf", sample_pdf, "application/pdf")},
        data={"privacy_accepted": "false"},
        headers={"X-Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "PRIVACY_NOT_ACCEPTED"
```

---

### TC-API-002：計算結果端點 — 完整回應結構驗證

```python
async def test_get_results_structure(client, completed_calculation_id):
    response = await client.get(f"/api/v1/results/{completed_calculation_id}")
    assert response.status_code == 200
    data = response.json()["data"]

    # 必要欄位驗證
    assert "entry_summary" in data
    assert "duty_components" in data
    assert "total_duty" in data
    assert "estimated_refund" in data
    assert data["refund_pathway"] in ("PSC", "PROTEST", "INELIGIBLE")
    assert "disclaimer_text" in data

    # duty_components 至少含 MFN 和 IEEPA
    types = {c["tariff_type"] for c in data["duty_components"]}
    assert "MFN" in types
    assert "IEEPA" in types
    assert "MPF" in types
```

---

### TC-API-003：Lead 提交端點

```python
async def test_lead_submission(client, completed_calculation_id):
    response = await client.post("/api/v1/leads", json={
        "full_name": "Jane Smith",
        "company_name": "ABC Trading Inc.",
        "email": "jane@abc.com",
        "country": "US",
        "preferred_contact": "email",
        "contact_consent": True,
        "calculation_id": completed_calculation_id,
    })
    assert response.status_code == 201
    assert response.json()["data"]["crm_sync_status"] == "pending"

async def test_lead_duplicate_rejected(client, completed_calculation_id):
    payload = { ... }  # 同上
    await client.post("/api/v1/leads", json=payload)
    response = await client.post("/api/v1/leads", json=payload)  # 第二次
    assert response.status_code == 409
    assert response.json()["error"] == "LEAD_ALREADY_EXISTS"
```

---

### TC-API-004：Auth 流程

```python
async def test_auth_full_flow(client):
    # 1. 註冊
    reg = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com", "password": "Secure!Pass123",
        "password_confirm": "Secure!Pass123", "full_name": "Test User",
    })
    assert reg.status_code == 201
    assert reg.json()["data"]["is_active"] is False

    # 2. 未驗證前無法登入
    login = await client.post("/api/v1/auth/token",
                               json={"email": "test@example.com", "password": "Secure!Pass123"})
    assert login.status_code == 403
    assert login.json()["error"] == "EMAIL_NOT_VERIFIED"

    # 3. 模擬 Email 驗證
    token = await get_verification_token_from_db("test@example.com")
    verify = await client.get(f"/api/v1/auth/verify?token={token}")
    assert verify.status_code == 200

    # 4. 驗證後可登入
    login2 = await client.post("/api/v1/auth/token",
                                json={"email": "test@example.com", "password": "Secure!Pass123"})
    assert login2.status_code == 200
    assert "access_token" in login2.json()["data"]
    assert "refresh_token" in login2.cookies
```

---

### TC-API-005：Admin 端點存取控制

```python
async def test_admin_endpoint_requires_admin_role(client, user_token):
    # 普通用戶無法存取 Admin API
    response = await client.get(
        "/api/v1/admin/rates",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403

async def test_admin_endpoint_no_token(client):
    response = await client.get("/api/v1/admin/rates")
    assert response.status_code == 401

async def test_admin_endpoint_expired_token(client, expired_admin_token):
    response = await client.get(
        "/api/v1/admin/rates",
        headers={"Authorization": f"Bearer {expired_admin_token}"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "Token expired"
```

---

### TC-API-006：Rate Limit 驗證

```python
async def test_upload_rate_limit(client, sample_pdf):
    """每 IP 每小時 10 次上傳限制"""
    for i in range(10):
        r = await client.post("/api/v1/documents/upload",
                               files={"file": ("f.pdf", sample_pdf, "application/pdf")},
                               data={"privacy_accepted": "true"},
                               headers={"X-Idempotency-Key": str(uuid4())})
        assert r.status_code == 202

    # 第 11 次應被限制
    r = await client.post("/api/v1/documents/upload",
                           files={"file": ("f.pdf", sample_pdf, "application/pdf")},
                           data={"privacy_accepted": "true"},
                           headers={"X-Idempotency-Key": str(uuid4())})
    assert r.status_code == 429
    assert "Retry-After" in r.headers

async def test_login_brute_force_protection(client):
    """每 IP 每分鐘 5 次登入限制"""
    for _ in range(5):
        await client.post("/api/v1/auth/token",
                          json={"email": "x@x.com", "password": "wrong"})
    r = await client.post("/api/v1/auth/token",
                          json={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 429
```

---

### TC-API-007：Download Token 時效驗證

```python
async def test_download_token_expires(client, expired_download_token):
    response = await client.get(f"/api/v1/files/download?token={expired_download_token}")
    assert response.status_code == 403
    assert response.json()["error"] == "TOKEN_EXPIRED"

async def test_download_token_tampered(client, valid_download_token):
    tampered = valid_download_token[:-4] + "XXXX"
    response = await client.get(f"/api/v1/files/download?token={tampered}")
    assert response.status_code == 403
    assert response.json()["error"] == "INVALID_TOKEN"
```

---

## 8.1.4 Security Tests（資安測試）

### TC-SEC-001：HTTP 安全標頭完整性

```python
async def test_security_headers(client):
    response = await client.get("/")
    headers = response.headers
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
    assert "max-age=31536000" in headers.get("Strict-Transport-Security", "")
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
```

---

### TC-SEC-002：PII 欄位加密驗證

```python
async def test_pii_encrypted_at_rest(client, db_session, completed_calculation_id):
    # 提交 Lead
    await client.post("/api/v1/leads", json={
        "full_name": "Jane Smith",
        "email": "jane@abc.com",
        ...
    })
    # 直接查詢 DB（不經過 API）
    lead = await db_session.execute(
        select(Lead).where(Lead.calculation_id == completed_calculation_id)
    )
    lead_row = lead.scalar_one()
    # DB 中儲存的值應為加密密文，而非明文
    assert lead_row.email != "jane@abc.com"
    assert lead_row.full_name != "Jane Smith"
    assert len(lead_row.email) > 50  # Fernet token 遠長於原文
```

---

### TC-SEC-003：SQL 注入防護

```python
@pytest.mark.parametrize("malicious_input", [
    "'; DROP TABLE users; --",
    "1' OR '1'='1",
    "\" OR \"\"=\"",
    "admin'--",
])
async def test_sql_injection_prevention(client, malicious_input):
    response = await client.post("/api/v1/auth/token", json={
        "email": malicious_input,
        "password": "anything",
    })
    # 應回傳 401/400，而非 200 或 500
    assert response.status_code in (400, 401, 422)
    # 資料庫不應被修改（透過 users 表計數驗證）
```

---

### TC-SEC-004：上傳檔案 Magic Bytes 驗證

```python
async def test_exe_renamed_as_pdf_rejected(client):
    # 建立一個有 PE header 但副檔名為 .pdf 的假檔案
    fake_content = b"MZ\x90\x00" + b"\x00" * 100
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("legit.pdf", fake_content, "application/pdf")},
        data={"privacy_accepted": "true"},
        headers={"X-Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 415
    assert response.json()["error"] == "UNSUPPORTED_FILE_TYPE"
```

---

### TC-SEC-005：Session 跨使用者隔離

```python
async def test_session_isolation(client, sample_pdf):
    # 使用者 A 上傳文件
    r_a = await client.post("/api/v1/documents/upload",
                             files={"file": ("f.pdf", sample_pdf, "application/pdf")},
                             data={"privacy_accepted": "true"},
                             headers={"X-Idempotency-Key": str(uuid4())})
    job_id = r_a.json()["data"]["job_id"]

    # 使用者 B（不同 session）嘗試存取 A 的文件
    client_b = AsyncClient(...)  # 全新 client，無 session_id cookie
    r_b = await client_b.get(f"/api/v1/documents/{job_id}/status")
    assert r_b.status_code == 403
```

---

### TC-SEC-006：靜態分析（CI 自動執行）

```bash
# bandit — Python 安全靜態分析
bandit -r app/ -ll --exit-zero-on-skipped
# 零個 HIGH 或 CRITICAL 問題（B608: SQL injection 特別關注）

# pip-audit — 依賴漏洞掃描
pip-audit --requirement requirements.txt
# 零個 CRITICAL 漏洞

# npm audit — 前端依賴掃描
cd frontend && npm audit --audit-level=critical
```

---

## 8.1.5 Frontend / UI Tests（前端測試）

### TC-FE-001：上傳按鈕在未勾選隱私條款時 disabled

```typescript
// Vitest + React Testing Library
test("upload button is disabled until privacy checkbox checked", () => {
  render(<CalculatorPage />);
  const uploadButton = screen.getByRole("button", { name: /upload/i });
  expect(uploadButton).toBeDisabled();

  fireEvent.click(screen.getByRole("checkbox", { name: /privacy notice/i }));
  expect(uploadButton).not.toBeDisabled();
});
```

---

### TC-FE-002：低信心欄位 Amber 高亮

```typescript
test("review_required fields have amber border class", () => {
  const mockFields = {
    summary_date: { value: "2026-02-15", confidence: 0.72, review_required: true },
    entry_number: { value: "ABC-1234567-8", confidence: 0.98, review_required: false },
  };
  render(<ReviewPage fields={mockFields} />);

  const amberField = screen.getByTestId("field-summary_date");
  expect(amberField).toHaveClass("border-amber-500");

  const normalField = screen.getByTestId("field-entry_number");
  expect(normalField).not.toHaveClass("border-amber-500");
});
```

---

### TC-FE-003：Results 頁 IEEPA 行高亮 + 免責聲明不可隱藏

```typescript
test("IEEPA row has highlight background", () => {
  render(<ResultsPage calculationId="test-id" />);
  const ieepaRow = screen.getByTestId("duty-row-IEEPA");
  expect(ieepaRow).toHaveClass("bg-yellow-50");
});

test("disclaimer banner is always visible and not dismissible", () => {
  render(<ResultsPage calculationId="test-id" />);
  const disclaimer = screen.getByRole("alert", { name: /disclaimer/i });
  expect(disclaimer).toBeInTheDocument();
  // 確認沒有關閉按鈕
  expect(within(disclaimer).queryByRole("button", { name: /close|dismiss/i })).toBeNull();
});
```

---

### TC-FE-004：PSC/PROTEST/INELIGIBLE 各顯示正確色彩

```typescript
test.each([
  ["PSC",        "text-green-700",  "bg-green-50"],
  ["PROTEST",    "text-amber-700",  "bg-amber-50"],
  ["INELIGIBLE", "text-red-700",    "bg-red-50"],
])("pathway %s displays correct colour", (pathway, textClass, bgClass) => {
  render(<PathwayBadge pathway={pathway} />);
  const badge = screen.getByTestId("pathway-badge");
  expect(badge).toHaveClass(textClass);
  expect(badge).toHaveClass(bgClass);
});
```

---

### TC-FE-005：語系切換

```typescript
test("language toggle switches all UI text", async () => {
  render(<App />);
  expect(screen.getByText(/Start Calculating/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /中文/i }));
  await waitFor(() => {
    expect(screen.getByText(/開始計算/i)).toBeInTheDocument();
    expect(screen.queryByText(/Start Calculating/i)).toBeNull();
  });
});
```

---

### TC-FE-006：Lead 表單 Zod 驗證

```typescript
test("invalid email shows error message", async () => {
  render(<RegisterPage calculationId="test-id" />);
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "not-an-email" } });
  fireEvent.click(screen.getByRole("button", { name: /download/i }));
  await waitFor(() => {
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
  });
});
```

---

## 8.1.6 E2E Test Scenarios（端到端測試）

> 使用 Playwright 對 Staging 環境執行，所有測試後清理測試資料。

### TC-E2E-001：Guest 單筆上傳完整流程

```
1. 開啟 /calculate
2. 勾選隱私條款
3. 上傳測試 Form 7501 PDF
4. 等待 OCR 完成（輪詢狀態，最長等 60 秒）
5. 在 /review 確認所有欄位（修正 1 個 Amber 欄位）
6. 點擊 [Confirm & Calculate]
7. 等待計算完成（最長 30 秒）
8. 在 /results 確認：
   - 退稅金額 > $0
   - IEEPA 行有高亮背景
   - refund_pathway 為 PSC / PROTEST / INELIGIBLE 之一
   - 免責聲明 Banner 存在且無關閉按鈕
9. 點擊 [Download PDF Report]
10. 在 /register 填寫 Lead 表單
11. 確認 PDF 下載成功
```

---

### TC-E2E-002：Registered User 批量上傳流程

```
1. 登入 Registered User 帳號
2. 開啟 /bulk
3. 下載 CSV 範本
4. 上傳填好的 10 列 CSV
5. 確認 Progress Dashboard 顯示進度
6. 等待所有 Job 完成
7. 確認結果：
   - total_refundable 顯示正確加總
   - pathway_breakdown 各數字加總等於 total_entries
   - 可點擊 [Export CSV] 下載結果
```

---

### TC-E2E-003：Admin 稅率更新流程

```
1. 以 Admin 帳號登入
2. 進入 /admin/rates
3. 搜尋 HTS Code "8471300100"
4. 點擊 [Edit]，修改 IEEPA rate 從 20.0% 為 25.0%
5. 儲存後確認：
   - 列表顯示新稅率 25.0%
   - audit_log 新增一筆記錄
   - Redis 快取被清除（可透過後續計算驗證使用新稅率）
6. 使用新稅率執行一次計算，確認結果反映 25%
```

---

## 8.1.7 Performance Tests（效能測試）

### TC-PERF-001：500 並發使用者負載測試

```javascript
// k6 腳本
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 500,
  duration: '10m',
  thresholds: {
    http_req_duration: ['p(95)<500'],  // P95 ≤ 500ms
    http_req_failed: ['rate<0.01'],     // 錯誤率 < 1%
  },
};

export default function () {
  const res = http.get('https://staging.ieepa.dimerco.local/api/v1/results/test-id');
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
```

---

### TC-PERF-002：OCR 處理時間（P95 ≤ 30 秒）

```python
@pytest.mark.performance
async def test_ocr_processing_time_p95(ocr_engine, test_corpus_dir):
    """100 次連續測試，P95 處理時間 ≤ 30 秒"""
    durations = []
    for doc_path in list(Path(test_corpus_dir).glob("*.pdf"))[:100]:
        start = time.monotonic()
        await ocr_engine.extract(doc_path)
        durations.append(time.monotonic() - start)

    p95 = sorted(durations)[int(len(durations) * 0.95)]
    assert p95 <= 30.0, f"OCR P95 duration {p95:.1f}s exceeds 30s"
```

---

### TC-PERF-003：計算引擎回應時間（P95 ≤ 2 秒）

```python
@pytest.mark.performance
async def test_calculation_engine_p95(client):
    """觸發 50 次計算，P95 ≤ 2 秒"""
    durations = []
    for _ in range(50):
        start = time.monotonic()
        job_id = await create_test_document_with_ocr(client)
        await client.post(f"/api/v1/documents/{job_id}/calculate",
                          headers={"X-Idempotency-Key": str(uuid4())})
        await wait_for_calculation_complete(client, job_id)
        durations.append(time.monotonic() - start)

    p95 = sorted(durations)[int(len(durations) * 0.95)]
    assert p95 <= 2.0, f"Calculation P95 {p95:.2f}s exceeds 2s"
```

---

### TC-PERF-004：Redis 快取命中率

```python
async def test_redis_cache_hit_rate(client):
    """HTS 稅率查詢快取命中率 ≥ 95%（穩態負載下）"""
    # 執行 100 次相同 HTS 的計算
    for _ in range(100):
        await trigger_calculation_for_hts("8471300100", client)

    stats = await get_redis_stats()
    hit_rate = stats["keyspace_hits"] / (stats["keyspace_hits"] + stats["keyspace_misses"])
    assert hit_rate >= 0.95
```

---

*Prepared by the Office of the CIO, Dimerco Express Group | Version 1.0 | March 2026 | Confidential*
