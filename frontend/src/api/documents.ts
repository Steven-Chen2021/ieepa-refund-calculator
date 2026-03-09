import apiClient from './client'

export interface UploadResponse {
  job_id: string
  status: string
  expires_at: string
}

export interface OcrField {
  value: string
  confidence: number
  review_required: boolean
  read_failed: boolean  // confidence < 0.50 per 7501_Parse.md §3
}

export interface LineItem {
  line_number?: number
  hts_code: OcrField
  entered_value?: OcrField
  duty_rate?: OcrField
  duty_amount?: OcrField
  country_of_origin?: OcrField
  description?: OcrField
  /** True for IEEPA 退稅目標 codes: 9903.01.24 / 9903.01.25 */
  is_ieepa: boolean
  /** "main" | "S301" | "IEEPA" | "other_supplemental" */
  tariff_category: string
}

export interface ExtractedFields {
  // Box 1
  filer_code?: OcrField
  entry_number?: OcrField
  // Box 2
  entry_type?: OcrField
  // Box 3
  summary_date?: OcrField
  // Box 11
  import_date?: OcrField
  // Box 12
  bl_number?: OcrField
  // Box 37
  total_duty?: OcrField
  // Other header fields
  country_of_origin?: OcrField
  importer_name?: OcrField
  mode_of_transport?: OcrField
  port_of_entry?: OcrField
  port_code?: OcrField
  total_entered_value?: OcrField
  line_items?: LineItem[]
  review_required_count?: number
}

export interface JobStatusResponse {
  job_id: string
  status: 'queued' | 'processing' | 'completed' | 'review_required' | 'failed'
  ocr_provider?: string
  ocr_confidence?: number
  extracted_fields?: ExtractedFields
  error?: string
}

export interface CalculateResponse {
  calculation_id: string
}

/** Upload a CBP Form 7501 file */
export async function uploadDocument(
  file: File,
  idempotencyKey: string,
): Promise<UploadResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('privacy_accepted', 'true')

  const { data } = await apiClient.post<{ success: boolean; data: UploadResponse }>(
    '/documents/upload',
    form,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Idempotency-Key': idempotencyKey,
      },
    },
  )
  return data.data
}

/** Poll OCR job status */
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const { data } = await apiClient.get<{ success: boolean; data: JobStatusResponse }>(
    `/documents/${jobId}/status`,
  )
  return data.data
}

/** Save user corrections to OCR fields */
export async function patchFields(jobId: string, corrections: Record<string, unknown>): Promise<void> {
  await apiClient.patch(`/documents/${jobId}/fields`, corrections)
}

/** Trigger tariff calculation */
export async function calculate(jobId: string): Promise<CalculateResponse> {
  const { data } = await apiClient.post<{ success: boolean; data: CalculateResponse }>(
    `/documents/${jobId}/calculate`,
    {},
    { headers: { 'X-Idempotency-Key': `calc-${jobId}` } },
  )
  return data.data
}
