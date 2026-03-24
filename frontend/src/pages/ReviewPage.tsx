import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { calculate, getJobStatus, patchFields } from '../api/documents'
import type { ExtractedFields, LineItem, OcrField } from '../api/documents'
import StepIndicator from '../components/ui/StepIndicator'
import { useUploadStore } from '../store/uploadStore'

/** Derive display colour from OcrField confidence per 7501_Parse.md §3 */
function fieldColour(field: OcrField | undefined, edited: boolean): 'normal' | 'amber' | 'red' {
  if (edited || !field) return 'normal'
  if (field.read_failed || field.confidence < 0.5) return 'red'
  if (field.review_required || field.confidence < 0.80) return 'amber'
  return 'normal'
}

function TariffTypeBadge({ category }: { category: string }): JSX.Element {
  const { t } = useTranslation()
  if (category === 'IEEPA') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-orange-100 text-logo-orange-dark border border-logo-orange">
        ★ {t('review.ieepa_target')}
      </span>
    )
  }
  if (category === 'S301') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-logo-orange-dark border border-logo-orange">
        {t('review.s301_label')}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-brand-gray">
      {t('review.main_label')}
    </span>
  )
}

function FieldCell({
  field,
  onEdit,
  showConfidence = true,
}: {
  field: OcrField | undefined
  onEdit: (val: string) => void
  showConfidence?: boolean
}): JSX.Element {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(field?.value ?? '')
  const [edited, setEdited] = useState(false)

  if (!field) return <span className="text-gray-400">—</span>

  const colour = showConfidence ? fieldColour(field, edited) : 'normal'
  const pct = Math.round((field.confidence ?? 0) * 100)

  if (editing) {
    return (
      <input
        autoFocus
        className="border border-logo-blue rounded px-2 py-1 text-sm w-full font-mono text-navy-blue outline-none ring-1 ring-logo-blue"
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

  const borderCls =
    colour === 'red'
      ? 'border-error bg-red-50'
      : colour === 'amber'
        ? 'border-logo-orange bg-orange-50'
        : 'border-transparent hover:border-brand-gray'

  const hintCls =
    colour === 'red'
      ? 'text-error'
      : colour === 'amber'
        ? 'text-logo-orange-dark'
        : edited
          ? 'text-logo-blue'
          : 'text-brand-gray'

  const hintText: string | null =
    edited
      ? `✏ ${t('review.edited')}`
      : showConfidence
        ? colour === 'red'
          ? `✗ ${t('review.read_failed')}`
          : colour === 'amber'
            ? `⚠ ${t('review.confidence', { pct })}`
            : `✓ ${t('review.confidence', { pct })}`
        : null

  return (
    <div
      className={`group cursor-pointer rounded px-2 py-1 border transition-colors ${borderCls}`}
      onClick={() => setEditing(true)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setEditing(true) }}
      aria-label={`Edit field, current value: ${draft}`}
    >
      <p className="text-sm font-medium">{draft || '—'}</p>
      {hintText && <p className={`text-xs mt-0.5 ${hintCls}`}>{hintText}</p>}
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
  const [extractionMethod, setExtractionMethod] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!jobId) { navigate('/calculate'); return }
    getJobStatus(jobId)
      .then((res) => {
        setFields(res.extracted_fields ?? null)
        setExtractionMethod(res.extraction_method ?? null)
        setLoading(false)
      })
      .catch(() => { setError('Failed to load document data.'); setLoading(false) })
  }, [jobId, navigate])

  const amberCount =
    fields
      ? Object.entries(fields)
          .filter(([k, v]) => k !== 'line_items' && k !== 'review_required_count' && (v as OcrField)?.review_required)
          .length +
        (fields.line_items?.reduce(
          (acc, li) =>
            acc +
            Object.values(li)
              .filter((f): f is OcrField => typeof f === 'object' && f !== null && 'review_required' in f)
              .filter((f) => f.review_required).length,
          0,
        ) ?? 0)
      : 0

  const isDirectRead = extractionMethod === 'direct_text'

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
      <div className="max-w-4xl mx-auto px-4 py-8 text-center text-brand-gray font-body">
        <div className="w-8 h-8 border-4 border-gray-200 border-t-navy-blue rounded-full animate-spin mx-auto mb-4" />
        {t('common.loading')}
      </div>
    )
  }

  // ── Header field config: [i18nKey, fieldKey] ──────────────────────────────
  const headerFieldDefs: [string, keyof ExtractedFields][] = [
    ['review.filer_code',    'filer_code'],
    ['review.entry_number',  'entry_number'],
    ['review.entry_type',    'entry_type'],
    ['review.summary_date',  'summary_date'],
    ['review.import_date',   'import_date'],
    ['review.bl_number',     'bl_number'],
    ['review.country_origin','country_of_origin'],
    ['review.importer',      'importer_name'],
    ['review.transport',     'mode_of_transport'],
    ['review.port',          'port_of_entry'],
    ['review.total_duty_ocr','total_duty'],
  ]

  // Group line items by line_number for visual separation (7501_Parse.md §2B)
  const groupedLines: Map<number | string, LineItem[]> = new Map()
  fields?.line_items?.forEach((li, idx) => {
    const key = li.line_number ?? idx
    const group = groupedLines.get(key) ?? []
    group.push(li)
    groupedLines.set(key, group)
  })

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 font-body text-navy-blue">
      <StepIndicator current={2} />

      <h1 className="text-2xl font-heading font-semibold text-navy-blue mb-1">{t('review.title')}</h1>
      <p className="text-dark-gray text-sm mb-6">
        {t(isDirectRead ? 'review.subtitle_direct' : 'review.subtitle')}
      </p>

      {/* Amber warning banner — only shown when OCR confidence indicators are relevant */}
      {!isDirectRead && amberCount > 0 && (
        <div className="mb-6 flex items-center gap-3 bg-orange-50 border border-logo-orange text-logo-orange-dark rounded-none rounded-br-lg p-4 text-sm font-medium">
          <span className="text-lg">⚠️</span>
          {t('review.amber_warning_other', { count: amberCount })}
        </div>
      )}

      {error && (
        <div className="mb-4 bg-red-50 border border-error text-error rounded-none rounded-br-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Header fields */}
      <div className="bg-white border border-gray-200 rounded-none rounded-br-lg p-5 mb-6 shadow-sm">
        <h2 className="text-sm font-heading font-semibold text-dark-gray uppercase tracking-wide mb-4">
          {t('review.header_fields')}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {headerFieldDefs.map(([labelKey, fieldKey]) => (
            <div key={fieldKey}>
              <label className="text-xs text-brand-gray font-medium uppercase tracking-wide">
                {t(labelKey)}
              </label>
              <FieldCell
                field={fields?.[fieldKey] as OcrField | undefined}
                onEdit={(v) => setField(fieldKey, v)}
                showConfidence={!isDirectRead}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Line items grouped by line_number (Box 27/29/33) */}
      {fields?.line_items && fields.line_items.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-none rounded-br-lg overflow-hidden mb-6 shadow-sm">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center gap-2">
            <h2 className="text-sm font-heading font-semibold text-dark-gray uppercase tracking-wide">
              {t('review.line_items')}
            </h2>
            <span className="ml-auto flex items-center gap-1 text-xs text-logo-orange bg-orange-50 border border-logo-orange px-2 py-0.5 rounded-full font-bold">
              ★ {t('review.ieepa_target')}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-white border-b border-gray-200">
                <tr>
                  {(['col_line','col_hts','col_tariff_type','col_rate','col_amount'] as const).map((k) => (
                    <th key={k} className="px-4 py-2 text-left text-xs font-heading font-semibold text-dark-gray uppercase tracking-wide">
                      {t(`review.${k}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Array.from(groupedLines.entries()).map(([lineKey, group]) => (
                  group.map((li, rowIdx) => {
                    const isIeepa = li.is_ieepa
                    const isFirstInGroup = rowIdx === 0
                    const isLastInGroup = rowIdx === group.length - 1
                    return (
                      <tr
                        key={`${lineKey}-${rowIdx}`}
                        className={[
                          isIeepa ? 'bg-orange-50' : 'hover:bg-gray-50',
                          isLastInGroup ? 'border-b-2 border-gray-200' : 'border-b border-gray-100',
                        ].join(' ')}
                      >
                        <td className="px-4 py-2 text-brand-gray font-mono">
                          {isFirstInGroup ? lineKey : ''}
                        </td>
                        <td className="px-4 py-2 font-mono">
                          <FieldCell
                            field={li.hts_code}
                            onEdit={(v) => setField(`line_items[${lineKey}][${rowIdx}].hts_code`, v)}
                            showConfidence={!isDirectRead}
                          />
                        </td>
                        <td className="px-4 py-2">
                          <TariffTypeBadge category={li.tariff_category} />
                        </td>
                        <td className="px-4 py-2">
                          {li.duty_rate ? (
                            <FieldCell
                              field={li.duty_rate}
                              onEdit={(v) => setField(`line_items[${lineKey}][${rowIdx}].duty_rate`, v)}
                              showConfidence={!isDirectRead}
                            />
                          ) : <span className="text-brand-gray">—</span>}
                        </td>
                        <td className="px-4 py-2">
                          {li.duty_amount ? (
                            <FieldCell
                              field={li.duty_amount}
                              onEdit={(v) => setField(`line_items[${lineKey}][${rowIdx}].duty_amount`, v)}
                              showConfidence={!isDirectRead}
                            />
                          ) : <span className="text-brand-gray">—</span>}
                        </td>
                      </tr>
                    )
                  })
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
          className="px-4 py-2 text-sm text-dark-gray border border-brand-gray bg-transparent font-heading font-semibold rounded-none hover:bg-gray-50 transition-colors"
        >
          {t('review.btn_back')}
        </button>
        <button
          onClick={handleConfirm}
          disabled={submitting}
          className={`flex items-center gap-2 px-6 py-3 font-heading font-semibold rounded-none rounded-br-lg text-white transition-opacity shadow-sm
            ${submitting ? 'bg-brand-gray cursor-not-allowed' : 'bg-gradient-to-b from-logo-orange to-logo-orange-dark hover:opacity-90 active:opacity-100'}`}
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
