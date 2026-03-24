import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import uploadCloudIcon from '../../icon/uploadCloud.png'
import checkIcon from '../../icon/check.png'
import walletIcon from '../../icon/wallet.png'

const STEPS = [
  { icon: uploadCloudIcon, titleKey: 'home.step1_title', descKey: 'home.step1_desc', num: 1 },
  { icon: checkIcon,       titleKey: 'home.step2_title', descKey: 'home.step2_desc', num: 2 },
  { icon: walletIcon,      titleKey: 'home.step3_title', descKey: 'home.step3_desc', num: 3 },
] as const


export default function HomePage(): JSX.Element {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col min-h-screen font-body bg-white text-navy-blue">

      {/* Page title with separator */}
      <div className="border-b border-gray-200 py-8 text-center bg-white">
        <h1 className="text-3xl font-heading font-bold text-gray-900">
          {t('home.hero_title')}
        </h1>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8 flex-1 w-full">

        {/* Description */}
        <p className="text-dark-gray mb-3 text-base">
          {t('home.hero_subtitle')}
        </p>

        {/* Orange notice */}
        <p className="text-logo-orange text-sm mb-10">
          {t('home.notice')}
        </p>

        {/* Section heading */}
        <h2 className="text-2xl font-heading font-bold text-gray-900 mb-6">
          {t('home.how_title')}
        </h2>

        {/* 3-step card */}
        <div className="border border-gray-200 rounded-lg overflow-hidden mb-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-gray-200">
            {STEPS.map(({ icon, titleKey, descKey, num }) => (
              <div key={num} className="p-6 bg-white">
                <div className="flex items-center gap-3 mb-3">
                  <div className="relative shrink-0">
                    <img src={icon} alt="" className="w-10 h-10 object-contain" />
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-navy-blue text-white text-xs font-bold rounded-full flex items-center justify-center">
                      {num}
                    </span>
                  </div>
                  <h3 className="font-heading font-semibold text-navy-blue text-sm">
                    {t(titleKey)}
                  </h3>
                </div>
                <p className="text-sm text-dark-gray leading-relaxed">
                  {t(descKey)}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="text-left">
          <Link
            to="/calculate"
            className="inline-flex items-center gap-2 px-8 py-3 bg-logo-orange text-white font-heading font-semibold rounded hover:bg-logo-orange-dark transition-colors shadow-sm"
          >
            {t('home.cta')}
            <span className="text-sm">→</span>
          </Link>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-5 px-4 bg-navy-blue text-brand-gray text-sm text-center">
        © 2026 Dimerco Express Group — Internal Tool — Confidential
      </footer>
    </div>
  )
}
