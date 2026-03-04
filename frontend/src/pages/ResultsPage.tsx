import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getResult } from '../api/results'
import type { CalculationResult, TariffLine } from '../api/results'
import PathwayBadge from '../components/ui/PathwayBadge'
import StepIndicator from '../components/ui/StepIndicator'

function usd(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function pct(n: number): string {
  return `${(n * 100).toFixed(4)}%`
}

const PATHWAY_ICON: Record<string, string> = { PSC: '✅', PROTEST: '⚠️', INELIGIBLE: '❌' }

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
      <div className="max-w-3xl mx-auto px-4 py-8">
        <StepIndicator current={3} />
        <div className="flex flex-col items-center py-20 gap-4 text-gray-500">
          <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-700 rounded-full animate-spin" />
          <p>Calculating tariffs…</p>
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

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <StepIndicator current={3} />

      {/* ── Refund callout ─────────────────────────────────── */}
      <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-2xl p-8 mb-6 text-center shadow-sm">
        <div className="text-3xl mb-2">💰</div>
        <p className="text-sm font-medium text-green-700 uppercase tracking-wide mb-1">
          {t('results.title')}
        </p>
        <p className="text-5xl font-bold text-green-700 font-mono mb-4">
          {usd(result.estimated_refund)}
        </p>
        <div className="flex flex-col items-center gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">{t('results.pathway_label')}:</span>
            <PathwayBadge pathway={result.refund_pathway} large />
          </div>
          <p className="text-sm text-gray-600 max-w-sm">
            {PATHWAY_ICON[result.refund_pathway]}{' '}
            {t(pathwayNameKey as never)}
          </p>
        </div>
      </div>

      {/* ── Entry summary ───────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6 shadow-sm">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          {t('results.entry_summary')}
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
          {[
            [t('results.entry_number'), result.entry_number],
            [t('results.summary_date'), result.summary_date],
            [t('results.country_origin'), result.country_of_origin],
            [t('results.port'), result.port_of_entry],
            [t('results.importer'), result.importer_name],
            [t('results.transport'), result.mode_of_transport],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
              <p className="font-medium text-gray-800">{value || '—'}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Duty breakdown table ────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-6 shadow-sm">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
            {t('results.duty_breakdown')}
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[
                  t('results.col_component'),
                  t('results.col_rate'),
                  t('results.col_amount'),
                  t('results.col_refundable'),
                ].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide"
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
                      ${isIeepa ? 'bg-yellow-50' : 'hover:bg-gray-50'}
                    `}
                  >
                    <td className="px-4 py-3 font-medium">
                      <span className={isIeepa ? 'text-amber-900' : 'text-gray-800'}>
                        {isIeepa && '★ '}{t(labelKey as never)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-gray-600">{pct(line.rate)}</td>
                    <td className="px-4 py-3 font-mono">{usd(line.amount)}</td>
                    <td className="px-4 py-3 text-center">
                      {line.refundable ? (
                        <span className="text-green-600 font-bold">{t('results.yes')}</span>
                      ) : (
                        <span className="text-gray-400">{t('results.no')}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {/* Total row */}
              <tr className="bg-gray-50 border-t-2 border-gray-200 font-bold">
                <td className="px-4 py-3 text-gray-800">{t('results.total')}</td>
                <td className="px-4 py-3" />
                <td className="px-4 py-3 font-mono">{usd(result.total_duty)}</td>
                <td className="px-4 py-3" />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Pathway explanation ─────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <PathwayBadge pathway={result.refund_pathway} large />
          <span className="font-semibold text-gray-800">{t(pathwayNameKey as never)}</span>
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
                        ? 'bg-amber-100 text-amber-700 border-amber-300'
                        : 'bg-red-100 text-red-700 border-red-300'
                    : 'bg-gray-100 text-gray-400 border-gray-200'
                }`}
              >
                {p}
              </span>
              {p !== 'INELIGIBLE' && <span className="text-gray-300">──</span>}
            </div>
          ))}
          <span className="ml-2 text-gray-400">({result.days_elapsed} days elapsed)</span>
        </div>
        <p className="text-sm text-gray-600">{t(pathwayDescKey as never)}</p>
      </div>

      {/* ── Action buttons ──────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 mb-6">
        <button
          onClick={() => window.alert('PDF export requires a logged-in session.')}
          className="flex items-center gap-2 px-5 py-3 bg-blue-800 text-white rounded-xl font-semibold hover:bg-blue-700 text-sm"
        >
          📄 {t('results.btn_download')}
        </button>
        <Link
          to="/calculate"
          className="flex items-center gap-2 px-5 py-3 border border-gray-300 text-gray-700 rounded-xl font-semibold hover:bg-gray-50 text-sm"
        >
          📋 {t('results.btn_new')}
        </Link>
      </div>

      {/* ── Lead CTA ────────────────────────────────────────── */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-6">
        <h3 className="font-semibold text-blue-900 mb-1">{t('results.lead_title')}</h3>
        <p className="text-sm text-blue-700 mb-3">{t('results.lead_desc')}</p>
        <Link to="/register" className="text-sm font-semibold text-blue-800 hover:underline">
          {t('results.lead_cta')}
        </Link>
      </div>

      {/* ── Mandatory disclaimer (COMP-005 — must not be hidden) ─── */}
      <div className="bg-gray-100 border border-gray-300 rounded-xl p-4 text-xs text-gray-500">
        <span className="font-semibold text-gray-700">⚠ Disclaimer: </span>
        {t('results.disclaimer')}
      </div>
    </div>
  )
}
