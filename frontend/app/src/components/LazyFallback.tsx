import { useTranslation } from "react-i18next";

// Suspense fallback-и для lazy-компонентів (modal/sheet) — компактний
// спінер замість білого екрана, поки чанк вантажиться.
export function LazySpinner() {
  const { t } = useTranslation();
  return <span className="lazy-spinner" role="status" aria-label={t("common.loadingAriaLabel")} />;
}

export function LazyOverlayFallback() {
  return (
    <div className="lazy-fallback-overlay">
      <LazySpinner />
    </div>
  );
}

export function LazySheetFallback() {
  return (
    <div className="lazy-fallback-sheet">
      <div className="lazy-fallback-sheet-inner">
        <LazySpinner />
      </div>
    </div>
  );
}

export function LazyInlineFallback() {
  return (
    <div className="lazy-fallback-inline">
      <LazySpinner />
    </div>
  );
}

// Показується замість компонента, коли чанк не вантажиться навіть після
// одного reload (lazyWithRetry) — постійна відмова мережі/CDN, не варто
// зациклюватись на reload.
export function ChunkLoadError() {
  const { t } = useTranslation();
  return <p className="status-text chunk-load-error">{t("errors.chunkLoad")}</p>;
}
