/**
 * SkladBase — інтеграція з Telegram WebApp SDK (Стадія 7a).
 *
 * `initTelegram()` викликається один раз при старті: ready()+expand() і
 * theme params -> CSS-змінні `--tg-*` (бекграунд/текст/кнопки тощо, як у
 * клієнта користувача). Брендинг магазину (accent_color) — окремо, через
 * `setAccentColor()`, бо це дані з нашого API, не з Telegram.
 */

interface TelegramThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  [key: string]: string | undefined;
}

interface TelegramWebApp {
  initData: string;
  themeParams: TelegramThemeParams;
  colorScheme?: "light" | "dark";
  ready: () => void;
  expand: () => void;
  openInvoice?: (url: string, callback?: (status: string) => void) => void;
  openTelegramLink?: (url: string) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

function applyThemeParams(theme: TelegramThemeParams): void {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(theme)) {
    if (!value) continue;
    root.style.setProperty(`--tg-${key.replace(/_/g, "-")}`, value);
  }
}

export function initTelegram(): void {
  const webApp = window.Telegram?.WebApp;
  if (!webApp) return;

  webApp.ready();
  webApp.expand();
  applyThemeParams(webApp.themeParams);
}

/** initData з реального Telegram-клієнта; у dev-режимі поза Telegram —
 * фолбек на VITE_DEV_INIT_DATA (валідний initData з scripts/dev_initdata.py). */
export function getInitData(): string {
  const fromTelegram = window.Telegram?.WebApp?.initData;
  if (fromTelegram) return fromTelegram;

  if (import.meta.env.DEV) {
    const devInitData = import.meta.env.VITE_DEV_INIT_DATA;
    if (devInitData) return devInitData;
  }

  return "";
}

/** Брендинг магазину (з GET /api/me) — accent_color у CSS-змінну. */
export function setAccentColor(color: string): void {
  document.documentElement.style.setProperty("--accent-color", color);
}

/** Відкриває інвойс Stars у клієнті Telegram. Поза Telegram (звичайний браузер)
 * `openInvoice` недоступний — повертає `false`, щоб викликач показав лінк сам. */
export function openInvoice(link: string, onClose?: (status: string) => void): boolean {
  const webApp = window.Telegram?.WebApp;
  if (!webApp?.openInvoice) return false;
  webApp.openInvoice(link, onClose);
  return true;
}

/** Ділиться інвайт-лінком через нативний Telegram-шер: `openTelegramLink` на
 * `t.me/share/url` — офіційно рекомендований спосіб для Mini Apps, працює
 * однаково на iOS/Android/Desktop (на відміну від window.open, якого
 * WebView може заблокувати). Поза Telegram — фолбек на Web Share API.
 * Якщо й того нема — повертає `false`: викликач лишає поле з лінком для
 * копіювання як універсальний запасний варіант. */
export function shareInviteLink(url: string, text: string): boolean {
  const webApp = window.Telegram?.WebApp;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;

  if (webApp?.openTelegramLink) {
    webApp.openTelegramLink(shareUrl);
    return true;
  }
  if (navigator.share) {
    void navigator.share({ url, text }).catch(() => {
      // юзер скасував/шер не спрацював — поле з лінком лишається як фолбек
    });
    return true;
  }
  return false;
}
