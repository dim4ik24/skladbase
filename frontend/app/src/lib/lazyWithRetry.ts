import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { ChunkLoadError } from "../components/LazyFallback";

const RELOAD_FLAG = "skladbase:chunk-reload-attempted";

function hasAlreadyRetried(): boolean {
  try {
    return sessionStorage.getItem(RELOAD_FLAG) === "1";
  } catch {
    // Приватний режим/quota — без sessionStorage не можемо відрізнити
    // перший фейл від повторного, тож не ризикуємо reload-петлею.
    return true;
  }
}

function markRetried(): void {
  try {
    sessionStorage.setItem(RELOAD_FLAG, "1");
  } catch {
    // ignore
  }
}

/**
 * React.lazy, стійкий до 404 на чанк-файл після деплою: Telegram WebView
 * тримає вкладку відкритою днями зі старим index.html, а чанки попереднього
 * білда вже видалені з CDN. Один reload підтягує актуальний index.html;
 * якщо імпорт падає і ПІСЛЯ нього (sessionStorage-прапорець) — показуємо
 * повідомлення замість reload-петлі.
 */
// ComponentType<any>, не <unknown>: props types are checked contravariantly,
// so a constraint of ComponentType<unknown> rejects every real component
// (its concrete props type isn't assignable from `unknown`) under strict mode.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function lazyWithRetry<T extends ComponentType<any>>(
  importFn: () => Promise<{ default: T }>,
): LazyExoticComponent<T> {
  async function load(): Promise<{ default: T }> {
    try {
      return await importFn();
    } catch (error) {
      console.error("[lazyWithRetry] chunk import failed:", error);
      if (hasAlreadyRetried()) {
        return { default: ChunkLoadError as unknown as T };
      }
      markRetried();
      window.location.reload();
      // reload() не блокує виконання — тримаємо проміс незавершеним, щоб
      // Suspense не встиг відрендерити ChunkLoadError до фактичного релоаду.
      return new Promise<{ default: T }>(() => {});
    }
  }
  return lazy(load);
}
