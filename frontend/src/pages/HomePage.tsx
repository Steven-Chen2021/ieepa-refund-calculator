import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

const TRUST_ICONS = ['🏛️', '📊', '🗑️', '🔒']

export default function HomePage(): JSX.Element {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col min-h-screen">
      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-4 py-20 bg-gradient-to-b from-blue-50 to-white">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-800 text-sm font-medium px-3 py-1 rounded-full mb-6">
            <span>🇺🇸</span>
            <span>IEEPA Tariff Relief — Act Before Your Deadline</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight mb-4">
            {t('home.hero_title')}
          </h1>
          <p className="text-lg text-gray-600 mb-8">{t('home.hero_subtitle')}</p>
          <Link
            to="/calculate"
            className="inline-flex items-center gap-2 px-8 py-4 bg-blue-800 text-white text-lg font-semibold rounded-xl hover:bg-blue-700 active:bg-blue-900 transition-colors shadow-md"
          >
            <span>▶</span>
            {t('home.cta')}
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-gray-900 mb-10">{t('home.how_title')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {([
              { icon: '📄', titleKey: 'home.step1_title', descKey: 'home.step1_desc', num: 1 },
              { icon: '🔍', titleKey: 'home.step2_title', descKey: 'home.step2_desc', num: 2 },
              { icon: '💰', titleKey: 'home.step3_title', descKey: 'home.step3_desc', num: 3 },
            ] as const).map(({ icon, titleKey, descKey, num }) => (
              <div key={num} className="flex flex-col items-center text-center gap-3">
                <div className="relative">
                  <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center text-3xl">
                    {icon}
                  </div>
                  <span className="absolute -top-1 -right-1 w-6 h-6 bg-blue-800 text-white text-xs font-bold rounded-full flex items-center justify-center">
                    {num}
                  </span>
                </div>
                <h3 className="font-semibold text-gray-900">{t(titleKey)}</h3>
                <p className="text-sm text-gray-500">{t(descKey)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust indicators */}
      <section className="py-10 px-4 bg-gray-50 border-t border-gray-100">
        <div className="max-w-4xl mx-auto grid grid-cols-2 sm:grid-cols-4 gap-4">
          {(['trust1', 'trust2', 'trust3', 'trust4'] as const).map((key, i) => (
            <div key={key} className="flex items-center gap-2 text-sm text-gray-600">
              <span className="text-xl">{TRUST_ICONS[i]}</span>
              <span>{t(`home.${key}`)}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="py-6 px-4 bg-gray-800 text-gray-400 text-sm text-center">
        © 2026 Dimerco Express Group — Internal Tool — Confidential
      </footer>
    </div>
  )
}
