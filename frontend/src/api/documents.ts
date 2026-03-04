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
}

export interface LineItem {
  line_number: number
  hts_code: OcrField
  entered_value: OcrField
  duty_rate: OcrField
  duty_amount: OcrField
}

export interface ExtractedFields {
  entry_number?: OcrField
  summary_date?: OcrField
  country_of_origin?: OcrField
  entry_type?: OcrField
  importer_name?: OcrField
  mode_of_transport?: OcrField
  port_of_entry?: OcrField
  line_items?: LineItem[]
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
