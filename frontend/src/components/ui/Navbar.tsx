import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'

export default function Navbar(): JSX.Element {
  const { t, i18n } = useTranslation()
  const location = useLocation()

  const toggleLang = (): void => {
    i18n.changeLanguage(i18n.language === 'en' ? 'zh-CN' : 'en')
  }

  return (
    <nav className="fixed top-0 inset-x-0 z-50 h-16 bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-6xl mx-auto h-full px-4 flex items-center justify-between">
        {/* Logo + title */}
        <Link to="/" className="flex items-center gap-2 text-blue-800 font-bold text-lg">
          <span className="text-2xl">🔍</span>
          <span className="hidden sm:inline">{t('nav.title')}</span>
        </Link>

        {/* Right actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleLang}
            className="text-sm text-gray-600 hover:text-blue-800 border border-gray-300 rounded px-2 py-1 transition-colors"
            aria-label="Toggle language"
          >
            {t('nav.lang_toggle')}
          </button>
          {location.pathname !== '/calculate' && (
            <Link
              to="/calculate"
              className="hidden sm:inline-flex items-center px-4 py-2 bg-blue-800 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
            >
              {t('home.cta')}
            </Link>
          )}
        </div>
      </div>
    </nav>
  )
}
