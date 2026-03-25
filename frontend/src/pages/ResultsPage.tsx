import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getResult } from '../api/results'
import type { CalculationResult, DutyLineComponent, TariffLine } from '../api/results'
import PathwayBadge from '../components/ui/PathwayBadge'
import StepIndicator from '../components/ui/StepIndicator'

function usd(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function pct(n: number): string {
  return `${(n * 100).toFixed(4)}%`
}


export default function ResultsPage(): JSX.Element {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [result, setResult] = useState<CalculationResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pollCount, setPollCount] = useState(0)

  useEffect(() => {
    if (!id) { navigate('/calculate'); return }

    let cancelled = false
    const tryFetch = async (): Promise<void> => {
      try {
        const data = await getResult(id)
        if (!cancelled) { setResult(data); setLoading(false) }
      } catch (err: unknown) {
        const status = (err as { response?: { status?: number } })?.response?.status
        // 404 / 202 = still calculating — retry up to 15 times (30 s)
        if (status === 404 || status === 202) {
          setPollCount((c) => c + 1)
        } else {
          if (!cancelled) { setError('Failed to load results.'); setLoading(false) }
        }
      }
    }

    if (pollCount < 15) {
      const t = setTimeout(tryFetch, pollCount === 0 ? 0 : 2000)
      return () => { cancelled = true; clearTimeout(t) }
    } else {
      setError('Calculation is taking longer than expected. Please try again.')
      setLoading(false)
    }
  }, [id, navigate, pollCount])

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 font-body text-navy-blue">
        <StepIndicator current={3} />
        <div className="flex flex-col items-center py-20 gap-4 text-brand-gray">
          <div className="w-12 h-12 border-4 border-gray-200 border-t-navy-blue rounded-full animate-spin" />
          <p className="font-heading font-semibold">Calculating tariffs…</p>
        </div>
      </div>
    )
  }

  if (error || !result) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <StepIndicator current={3} />
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-6 text-center">
          <p className="font-medium mb-4">{error || t('common.error_title')}</p>
          <Link to="/calculate" className="px-4 py-2 bg-red-700 text-white rounded-lg text-sm">
            {t('common.retry')}
          </Link>
        </div>
      </div>
    )
  }

  const pathwayDescKey = `results.${result.refund_pathway.toLowerCase()}_desc` as const
  const pathwayNameKey = `results.${result.refund_pathway.toLowerCase()}_name` as const

  // Build duty lines in display order
  const ORDER: TariffLine['tariff_type'][] = ['MFN', 'IEEPA', 'S301', 'S232', 'MPF', 'HMF']
  const sortedLines = [...result.tariff_lines].sort(
    (a, b) => ORDER.indexOf(a.tariff_type) - ORDER.indexOf(b.tariff_type),
  )

  // Group per-HTS line components for detail table
  const COMP_ORDER = ['MFN', 'IEEPA', 'S301', 'S232']
  const linesByHts = new Map<string, DutyLineComponent[]>()
  for (const comp of result.line_duty_components ?? []) {
    if (!linesByHts.has(comp.hts_code)) linesByHts.set(comp.hts_code, [])
    linesByHts.get(comp.hts_code)!.push(comp)
  }
  for (const comps of linesByHts.values()) {
    comps.sort((a, b) => COMP_ORDER.indexOf(a.tariff_type) - COMP_ORDER.indexOf(b.tariff_type))
  }
  const htsGroups = Array.from(linesByHts.entries())

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 font-body text-navy-blue">
      <StepIndicator current={3} />

      {/* ── Refund callout ─────────────────────────────────── */}
      <div className="bg-gray-white border border-success rounded-none rounded-br-lg p-8 mb-6 text-center shadow-sm">
        <p className="text-sm font-heading font-semibold text-success uppercase tracking-wide mb-1">
          {t('results.title')}
        </p>
        <p className="text-5xl font-bold text-success font-mono mb-4">
          {usd(result.estimated_refund)}
        </p>
        <div className="flex flex-col items-center gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm text-dark-gray">{t('results.pathway_label')}:</span>
            <PathwayBadge pathway={result.refund_pathway} large />
          </div>
        </div>
      </div>

      {/* ── Entry summary ───────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-none rounded-br-lg p-5 mb-6 shadow-sm">
        <h2 className="text-sm font-heading font-semibold text-dark-gray uppercase tracking-wide mb-3">
          {t('results.entry_summary')}
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
          {[
            [t('results.entry_number'), result.filer_code ? `${result.filer_code} / ${result.entry_number}` : result.entry_number],
            [t('results.summary_date'), result.summary_date],
            [t('results.import_date'),  result.import_date],
            [t('results.bl_number'),    result.bl_number],
            [t('results.country_origin'), result.country_of_origin],
            [t('results.port'),         result.port_of_entry],
            [t('results.importer'),     result.importer_name],
            [t('results.transport'),    result.mode_of_transport],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="text-xs text-brand-gray uppercase tracking-wide">{label}</p>
              <p className="font-medium text-navy-blue">{value || '—'}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Duty breakdown table ────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-none rounded-br-lg overflow-hidden mb-6 shadow-sm">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-heading font-semibold text-dark-gray uppercase tracking-wide">
            {t('results.duty_breakdown')}
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-white border-b border-gray-200">
              <tr>
                {[
                  t('results.col_component'),
                  t('results.col_rate'),
                  t('results.col_amount'),
                  t('results.col_refundable'),
                ].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2 text-left text-xs font-heading font-semibold text-dark-gray uppercase tracking-wide"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedLines.map((line) => {
                const isIeepa = line.tariff_type === 'IEEPA'
                const labelKey = `results.${line.tariff_type.toLowerCase() as 'mfn' | 'ieepa' | 's301' | 's232' | 'mpf' | 'hmf'}`
                return (
                  <tr
                    key={line.tariff_type}
                    className={`border-b border-gray-100 last:border-0
                      ${isIeepa ? 'bg-orange-50' : 'hover:bg-gray-50'}
                    `}
                  >
                    <td className="px-4 py-3 font-medium">
                      <span className={isIeepa ? 'text-logo-orange-dark' : 'text-navy-blue'}>
                        {isIeepa && '★ '}{t(labelKey as never)}
                      </span>
                      {isIeepa && (
                        <p className="text-xs text-logo-orange mt-0.5 font-mono">
                          9903.01.24 / 9903.01.25
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-dark-gray">{pct(line.rate)}</td>
                    <td className="px-4 py-3 font-mono">{usd(line.amount)}</td>
                    <td className="px-4 py-3 text-center">
                      {line.refundable ? (
                        <span className="text-success font-bold">{t('results.yes')}</span>
                      ) : (
                        <span className="text-brand-gray">{t('results.no')}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {/* Total row */}
              <tr className="bg-gray-white border-t-2 border-gray-200 font-bold">
                <td className="px-4 py-3 text-navy-blue">{t('results.total')}</td>
                <td className="px-4 py-3" />
                <td className="px-4 py-3 font-mono">{usd(result.total_duty)}</td>
                <td className="px-4 py-3" />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Line item detail table ─────────────────────────── */}
      {htsGroups.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-none rounded-br-lg overflow-hidden mb-6 shadow-sm">
          <div className="px-5 py-3 border-b border-gray-100">
            <h2 className="text-sm font-heading font-semibold text-dark-gray uppercase tracking-wide">
              {t('results.line_detail')}
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-white border-b border-gray-200">
                <tr>
                  {[
                    t('results.col_hts'),
                    t('results.col_component'),
                    t('results.col_rate'),
                    t('results.col_amount'),
                    t('results.col_refundable'),
                  ].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2 text-left text-xs font-heading font-semibold text-dark-gray uppercase tracking-wide"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {htsGroups.map(([htsCode, comps], groupIdx) =>
                  comps.map((comp, rowIdx) => {
                    const isIeepa = comp.tariff_type === 'IEEPA'
                    const labelKey = `results.${comp.tariff_type.toLowerCase() as 'mfn' | 'ieepa' | 's301' | 's232'}`
                    const isFirstRow = rowIdx === 0
                    const isLastRow = rowIdx === comps.length - 1
                    const isLastGroup = groupIdx === htsGroups.length - 1
                    return (
                      <tr
                        key={`${htsCode}-${comp.tariff_type}`}
                        className={`
                          ${isIeepa ? 'bg-orange-50' : 'hover:bg-gray-50'}
                          ${!isLastRow || !isLastGroup ? 'border-b border-gray-100' : ''}
                          ${isFirstRow && groupIdx > 0 ? 'border-t-2 border-gray-200' : ''}
                        `}
                      >
                        <td className="px-4 py-2.5 font-mono text-xs text-brand-gray">
                          {isFirstRow ? htsCode : ''}
                        </td>
                        <td className="px-4 py-2.5 font-medium">
                          <span className={isIeepa ? 'text-logo-orange-dark' : 'text-navy-blue'}>
                            {isIeepa && '★ '}{t(labelKey as never)}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-dark-gray">{pct(comp.rate)}</td>
                        <td className="px-4 py-2.5 font-mono">{usd(comp.amount)}</td>
                        <td className="px-4 py-2.5 text-center">
                          {comp.refundable ? (
                            <span className="text-success font-bold">{t('results.yes')}</span>
                          ) : (
                            <span className="text-brand-gray">{t('results.no')}</span>
                          )}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Pathway explanation ─────────────────────────────── */}      <div className="bg-white border border-gray-200 rounded-none rounded-br-lg p-5 mb-6 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <PathwayBadge pathway={result.refund_pathway} large />
          <span className="font-heading font-semibold text-navy-blue">{t(pathwayNameKey as never)}</span>
        </div>
        {/* Timeline indicator */}
        <div className="flex items-center gap-1 mb-4 text-xs font-medium">
          {(['PSC', 'PROTEST', 'INELIGIBLE'] as const).map((p) => (
            <div key={p} className="flex items-center gap-1">
              <span
                className={`px-2 py-0.5 rounded border ${
                  p === result.refund_pathway
                    ? p === 'PSC'
                      ? 'bg-green-100 text-green-700 border-green-300'
                      : p === 'PROTEST'
                        ? 'bg-orange-100 text-logo-orange-dark border-logo-orange'
                        : 'bg-red-100 text-error border-red-300'
                    : 'bg-gray-100 text-brand-gray border-gray-200'
                }`}
              >
                {p}
              </span>
              {p !== 'INELIGIBLE' && <span className="text-brand-gray">──</span>}
            </div>
          ))}
          <span className="ml-2 text-brand-gray">({result.days_elapsed} days elapsed)</span>
        </div>
        <p className="text-sm text-dark-gray">{t(pathwayDescKey as never)}</p>
      </div>

      {/* ── Action buttons ──────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 mb-6">
        <Link
          to="/calculate"
          className="flex items-center gap-2 px-5 py-3 border border-logo-orange text-logo-orange bg-transparent rounded-none font-heading font-semibold hover:bg-orange-50 text-sm"
        >
          📋 {t('results.btn_new')}
        </Link>
      </div>

      {/* ── Lead CTA ────────────────────────────────────────── */}
      <div className="bg-gray-white border border-logo-blue rounded-none rounded-br-lg p-5 mb-6">
        <h3 className="font-heading font-semibold text-navy-blue mb-1">{t('results.lead_title')}</h3>
        <p className="text-sm text-dark-gray mb-3">{t('results.lead_desc')}</p>
        <a
          href="mailto:us.tradecompliance@dimerco.com"
          className="text-sm font-semibold text-logo-blue hover:underline"
        >
          {t('results.lead_cta')}
        </a>
      </div>

      {/* ── Mandatory disclaimer (COMP-005 — must not be hidden) ─── */}
      <div className="bg-gray-100 border border-gray-300 rounded-none rounded-br-lg p-4 text-xs text-brand-gray">
        <span className="font-semibold text-dark-gray">⚠ Disclaimer: </span>
        {t('results.disclaimer')}
      </div>
    </div>
  )
}
