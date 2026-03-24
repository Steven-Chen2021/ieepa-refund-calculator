import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import DimercoLogo from './DimercoLogo'

export default function Navbar(): JSX.Element {
  const { t, i18n } = useTranslation()
  const location = useLocation()

  const toggleLang = (): void => {
    i18n.changeLanguage(i18n.language === 'en' ? 'zh-CN' : 'en')
  }

  return (
    <nav className="fixed top-0 inset-x-0 z-50 h-16 bg-white border-b border-gray-200 shadow-sm font-body">
      <div className="max-w-6xl mx-auto h-full px-4 flex items-center justify-between">
        {/* Dimerco Logo */}
        <Link to="/" className="flex items-center">
          <DimercoLogo className="h-7 w-auto" />
        </Link>

        {/* Right actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleLang}
            className="text-sm text-dark-gray hover:text-navy-blue border border-gray-200 rounded px-2 py-1 transition-colors"
            aria-label="Toggle language"
          >
            {t('nav.lang_toggle')}
          </button>
          {location.pathname !== '/calculate' && (
            <Link
              to="/calculate"
              className="hidden sm:inline-flex items-center px-4 py-2 bg-logo-orange text-white font-heading font-semibold text-sm rounded-none rounded-br-lg hover:bg-logo-orange-dark transition-colors shadow-sm"
            >
              {t('home.cta')}
            </Link>
          )}
        </div>
      </div>
    </nav>
  )
}
