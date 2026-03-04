import apiClient from './client'

export type RefundPathway = 'PSC' | 'PROTEST' | 'INELIGIBLE'

export interface TariffLine {
  tariff_type: 'MFN' | 'IEEPA' | 'S301' | 'S232' | 'MPF' | 'HMF'
  rate: number
  amount: number
  refundable: boolean
}

export interface CalculationResult {
  calculation_id: string
  entry_number: string
  summary_date: string
  country_of_origin: string
  port_of_entry: string
  importer_name: string
  mode_of_transport: string
  estimated_refund: number
  refund_pathway: RefundPathway
  days_elapsed: number
  tariff_lines: TariffLine[]
  total_duty: number
  calculated_at: string
}

/** Fetch a completed calculation result */
export async function getResult(calculationId: string): Promise<CalculationResult> {
  const { data } = await apiClient.get<{ success: boolean; data: CalculationResult }>(
    `/results/${calculationId}`,
  )
  return data.data
}

/** Poll calculation status (returns same shape until ready) */
export async function getCalculationStatus(calculationId: string): Promise<{
  status: 'pending' | 'processing' | 'completed' | 'failed'
  result?: CalculationResult
}> {
  const { data } = await apiClient.get(`/results/${calculationId}/status`)
  return data.data
}
