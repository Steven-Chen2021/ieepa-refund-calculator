import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

const TRUST_ICONS = ['🏛️', '📊', '🗑️', '🔒']

export default function HomePage(): JSX.Element {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col min-h-screen font-body bg-gray-white text-navy-blue">
      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-4 py-20">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 bg-white border border-gray-200 text-navy-blue text-sm font-medium px-3 py-1 rounded-full mb-6 shadow-sm">
            <span>🇺🇸</span>
            <span>IEEPA Tariff Relief — Act Before Your Deadline</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-heading font-semibold text-navy-blue leading-tight mb-4">
            {t('home.hero_title')}
          </h1>
          <p className="text-lg text-dark-gray mb-8">{t('home.hero_subtitle')}</p>
          <Link
            to="/calculate"
            className="inline-flex items-center gap-2 px-8 py-4 bg-gradient-to-b from-logo-orange to-logo-orange-dark text-white text-lg font-heading font-semibold rounded-none rounded-br-lg hover:opacity-90 transition-opacity shadow-md"
          >
            <span>▶</span>
            {t('home.cta')}
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-heading font-semibold text-center text-navy-blue mb-10">{t('home.how_title')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {([
              { icon: '📄', titleKey: 'home.step1_title', descKey: 'home.step1_desc', num: 1 },
              { icon: '🔍', titleKey: 'home.step2_title', descKey: 'home.step2_desc', num: 2 },
              { icon: '💰', titleKey: 'home.step3_title', descKey: 'home.step3_desc', num: 3 },
            ] as const).map(({ icon, titleKey, descKey, num }) => (
              <div key={num} className="flex flex-col items-center text-center gap-3">
                <div className="relative">
                  <div className="w-16 h-16 rounded-full bg-gray-white border border-gray-100 flex items-center justify-center text-3xl text-navy-blue shadow-sm">
                    {icon}
                  </div>
                  <span className="absolute -top-1 -right-1 w-6 h-6 bg-navy-blue text-accent-cyan text-xs font-bold rounded-full flex items-center justify-center border border-white">
                    {num}
                  </span>
                </div>
                <h3 className="font-heading font-semibold text-navy-blue">{t(titleKey)}</h3>
                <p className="text-sm text-dark-gray">{t(descKey)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust indicators */}
      <section className="py-10 px-4 bg-gray-white border-t border-gray-200">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-4">
          {(['trust1', 'trust2', 'trust3', 'trust4'] as const).map((key, i) => (
            <div key={key} className="flex items-center gap-2 text-sm text-dark-gray">
              <span className="text-xl text-logo-blue">{TRUST_ICONS[i]}</span>
              <span>{t(`home.${key}`)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="py-6 px-4 bg-navy-blue text-brand-gray text-sm text-center">
        © 2026 Dimerco Express Group — Internal Tool — Confidential
      </footer>
    </div>
  )
}
