import { useTranslation } from 'react-i18next'
import type { RefundPathway } from '../../api/results'

interface Props {
  pathway: RefundPathway
  large?: boolean
}

const CONFIG: Record<RefundPathway, { badgeKey: string; bg: string; text: string; border: string }> = {
  PSC: {
    badgeKey: 'results.psc_badge',
    bg: 'bg-green-100',
    text: 'text-success-dark',
    border: 'border-success',
  },
  PROTEST: {
    badgeKey: 'results.protest_badge',
    bg: 'bg-orange-100',
    text: 'text-logo-orange-dark',
    border: 'border-logo-orange',
  },
  INELIGIBLE: {
    badgeKey: 'results.ineligible_badge',
    bg: 'bg-red-100',
    text: 'text-error',
    border: 'border-error',
  },
}

export default function PathwayBadge({ pathway, large = false }: Props): JSX.Element {
  const { t } = useTranslation()
  const cfg = CONFIG[pathway]

  return (
    <span
      className={`inline-flex items-center font-bold border rounded
        ${cfg.bg} ${cfg.text} ${cfg.border}
        ${large ? 'text-base px-4 py-1.5' : 'text-xs px-2 py-0.5'}
      `}
    >
      {t(cfg.badgeKey)}
    </span>
  )
}
