import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import uk from "./locales/uk.json";
import en from "./locales/en.json";
import ru from "./locales/ru.json";

export const SUPPORTED_LANGUAGES = ["uk", "en", "ru"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const LANG_KEY = "skladbase:lang";

function isSupportedLanguage(value: string | null): value is SupportedLanguage {
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(value ?? "");
}

// localStorage can throw in some WebViews (e.g. private mode) — fail silently.
function readStoredLanguage(): SupportedLanguage | null {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    return isSupportedLanguage(saved) ? saved : null;
  } catch {
    return null;
  }
}

export function setStoredLanguage(lang: SupportedLanguage): void {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // ignore
  }
}

/** Мова нового юзера з Telegram `language_code` (uk/en/ru), інакше uk.
 * localStorage має пріоритет — цю функцію викликаємо лише коли він порожній. */
function languageFromTelegram(): SupportedLanguage {
  const code = window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code;
  if (code?.startsWith("en")) return "en";
  if (code?.startsWith("ru")) return "ru";
  return "uk";
}

function resolveInitialLanguage(): SupportedLanguage {
  return readStoredLanguage() ?? languageFromTelegram();
}

void i18n
  .use(initReactI18next)
  .init({
    resources: {
      uk: { translation: uk },
      en: { translation: en },
      ru: { translation: ru },
    },
    lng: resolveInitialLanguage(),
    fallbackLng: "uk",
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
