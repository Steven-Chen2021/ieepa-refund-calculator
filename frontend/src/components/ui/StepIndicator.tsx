import { useTranslation } from 'react-i18next'

interface Props {
  current: 1 | 2 | 3
}

export default function StepIndicator({ current }: Props): JSX.Element {
  const { t } = useTranslation()

  const steps = [
    t('calculate.step_upload'),
    t('calculate.step_review'),
    t('calculate.step_results'),
  ]

  return (
    <div className="flex items-center justify-center gap-0 py-6">
      {steps.map((label, idx) => {
        const step = idx + 1
        const done = step < current
        const active = step === current

        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-heading font-semibold border-2 transition-colors
                  ${done ? 'bg-navy-blue border-navy-blue text-white' : ''}
                  ${active ? 'bg-white border-navy-blue text-navy-blue' : ''}
                  ${!done && !active ? 'bg-white border-gray-200 text-brand-gray' : ''}
                `}
              >
                {done ? '✓' : step}
              </div>
              <span
                className={`text-xs font-medium ${active ? 'text-navy-blue font-bold' : done ? 'text-navy-blue' : 'text-brand-gray'}`}
              >
                {label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`w-16 sm:w-24 h-0.5 mx-1 mb-5 transition-colors ${done ? 'bg-navy-blue' : 'bg-gray-200'}`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
