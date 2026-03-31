import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import './i18n';
import LanguageSwitcher from './components/LanguageSwitcher';

export default function App() {
  const { t, i18n } = useTranslation();

  useEffect(() => {
    const dir = i18n.language === 'he' ? 'rtl' : 'ltr';
    document.documentElement.dir = dir;
    document.documentElement.lang = i18n.language;
  }, [i18n.language]);

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-bold text-blue-400">{t('app_name')}</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-400">{t('language')}:</span>
          <LanguageSwitcher />
        </div>
      </header>

      {/* Main */}
      <main className="flex flex-col items-center justify-center min-h-[calc(100vh-64px)] gap-6 p-8">
        <h2 className="text-3xl font-semibold">{t('welcome')}</h2>
        <nav className="flex flex-wrap gap-3 justify-center">
          {['dashboard', 'machines', 'orders', 'alerts', 'settings'].map((key) => (
            <button
              key={key}
              className="px-4 py-2 bg-gray-700 hover:bg-blue-600 rounded-lg transition-colors text-sm font-medium"
            >
              {t(key)}
            </button>
          ))}
        </nav>
      </main>
    </div>
  );
}
