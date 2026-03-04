import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { calculate, getJobStatus, patchFields } from '../api/documents'
import type { ExtractedFields, OcrField } from '../api/documents'
import StepIndicator from '../components/ui/StepIndicator'
import { useUploadStore } from '../store/uploadStore'

function FieldCell({
  field,
  onEdit,
}: {
  field: OcrField | undefined
  onEdit: (val: string) => void
}): JSX.Element {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field?.value ?? '')
  const [edited, setEdited] = useState(false)

  if (!field) return <span className="text-gray-400">—</span>

  const amber = field.review_required && !edited
  const pct = Math.round((field.confidence ?? 0) * 100)

  if (editing) {
    return (
      <input
        autoFocus
        className="border border-blue-400 rounded px-2 py-1 text-sm w-full"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false)
          setEdited(true)
          onEdit(draft)
        }}
        onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
      />
    )
  }

  return (
    <div
      className={`group cursor-pointer rounded px-2 py-1 border transition-colors
        ${amber ? 'border-amber-400 bg-amber-50' : 'border-transparent hover:border-gray-300'}
      `}
      onClick={() => setEditing(true)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setEditing(true) }}
      aria-label={`Edit field, current value: ${draft}`}
    >
      <p className="text-sm font-medium">{draft || '—'}</p>
      <p className={`text-xs mt-0.5 ${amber ? 'text-amber-600' : edited ? 'text-blue-600' : 'text-gray-400'}`}>
        {edited
          ? `✏ ${t('review.edited')}`
          : amber
            ? `⚠ ${t('review.confidence', { pct })}`
            : `✓ ${t('review.confidence', { pct })}`}
      </p>
    </div>
  )
}

export default function ReviewPage(): JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const jobId = searchParams.get('job_id') ?? useUploadStore.getState().jobId ?? ''

  const { setCalculationId } = useUploadStore()

  const [fields, setFields] = useState<ExtractedFields | null>(null)
  const [corrections, setCorrections] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!jobId) { navigate('/calculate'); return }
    getJobStatus(jobId)
      .then((res) => { setFields(res.extracted_fields ?? null); setLoading(false) })
      .catch(() => { setError('Failed to load document data.'); setLoading(false) })
  }, [jobId, navigate])

  const amberCount =
    fields
      ? Object.entries(fields)
          .filter(([k, v]) => k !== 'line_items' && (v as OcrField)?.review_required)
          .length +
        (fields.line_items?.reduce(
          (acc, li) =>
            acc +
            Object.values(li)
              .filter((f): f is OcrField => typeof f === 'object' && 'review_required' in f)
              .filter((f) => f.review_required).length,
          0,
        ) ?? 0)
      : 0

  const handleConfirm = async (): Promise<void> => {
    setSubmitting(true)
    try {
      if (Object.keys(corrections).length > 0) await patchFields(jobId, corrections)
      const { calculation_id } = await calculate(jobId)
      setCalculationId(calculation_id)
      navigate(`/results/${calculation_id}`)
    } catch {
      setError('Failed to submit. Please try again.')
      setSubmitting(false)
    }
  }

  const setField = (key: string, val: string): void =>
    setCorrections((prev) => ({ ...prev, [key]: val }))

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8 text-center text-gray-500">
        <div className="w-8 h-8 border-4 border-blue-200 border-t-blue-700 rounded-full animate-spin mx-auto mb-4" />
        {t('common.loading')}
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <StepIndicator current={2} />

      <h1 className="text-2xl font-bold text-gray-900 mb-1">{t('review.title')}</h1>
      <p className="text-gray-500 text-sm mb-6">{t('review.subtitle')}</p>

      {/* Amber warning banner */}
      {amberCount > 0 && (
        <div className="mb-6 flex items-center gap-3 bg-amber-50 border border-amber-300 text-amber-800 rounded-xl p-4 text-sm font-medium">
          <span className="text-lg">⚠️</span>
          {t('review.amber_warning_other', { count: amberCount })}
        </div>
      )}

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          {error}
        </div>
      )}

      {/* Header fields */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
          {t('review.header_fields')}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            ['review.entry_number', 'entry_number'],
            ['review.summary_date', 'summary_date'],
            ['review.country_origin', 'country_of_origin'],
            ['review.entry_type', 'entry_type'],
            ['review.importer', 'importer_name'],
            ['review.transport', 'mode_of_transport'],
            ['review.port', 'port_of_entry'],
          ].map(([labelKey, fieldKey]) => (
            <div key={fieldKey}>
              <label className="text-xs text-gray-400 font-medium uppercase tracking-wide">
                {t(labelKey)}
              </label>
              <FieldCell
                field={fields?.[fieldKey as keyof ExtractedFields] as OcrField | undefined}
                onEdit={(v) => setField(fieldKey, v)}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Line items */}
      {fields?.line_items && fields.line_items.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-6 shadow-sm">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
              {t('review.line_items')}
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {['col_line', 'col_hts', 'col_value', 'col_rate', 'col_amount'].map((k) => (
                    <th key={k} className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      {t(`review.${k}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fields.line_items.map((li, idx) => (
                  <tr key={idx} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-400 font-mono">{li.line_number}</td>
                    <td className="px-4 py-2 font-mono">
                      <FieldCell
                        field={li.hts_code}
                        onEdit={(v) => setField(`line_items[${idx}].hts_code`, v)}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <FieldCell
                        field={li.entered_value}
                        onEdit={(v) => setField(`line_items[${idx}].entered_value`, v)}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <FieldCell
                        field={li.duty_rate}
                        onEdit={(v) => setField(`line_items[${idx}].duty_rate`, v)}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <FieldCell
                        field={li.duty_amount}
                        onEdit={(v) => setField(`line_items[${idx}].duty_amount`, v)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between mt-4">
        <button
          onClick={() => navigate('/calculate')}
          className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          {t('review.btn_back')}
        </button>
        <button
          onClick={handleConfirm}
          disabled={submitting}
          className={`flex items-center gap-2 px-6 py-3 font-semibold rounded-xl text-white transition-colors
            ${submitting ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-800 hover:bg-blue-700'}`}
        >
          {submitting && (
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          )}
          {t('review.btn_confirm')}
        </button>
      </div>
    </div>
  )
}
