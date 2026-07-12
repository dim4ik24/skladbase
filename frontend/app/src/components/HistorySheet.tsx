import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import * as api from "../api";
import { errorMessage } from "../errors";
import { RELEASE_REASON_LABELS, RETURN_REASON_LABELS, reasonLabel } from "../lib/financeReasons";
import { resolveProductPhoto } from "../lib/productPhoto";
import type { FinancePeriod, HistoryEvent, Product } from "../types";

interface HistorySheetProps {
  period: FinancePeriod;
  date?: string;
  products: Product[];
  onClose: () => void;
}

const EVENT_BADGE: Record<HistoryEvent["type"], { labelKey: string; className: string }> = {
  sale: { labelKey: "history.event.sale", className: "badge-event-sale" },
  return: { labelKey: "history.event.return", className: "badge-event-return" },
  release: { labelKey: "history.event.release", className: "badge-event-release" },
};

function formatEventDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${min}`;
}

function eventReasonLabel(event: HistoryEvent): string | null {
  if (!event.reason) return null;
  const map = event.type === "return" ? RETURN_REASON_LABELS : RELEASE_REASON_LABELS;
  return reasonLabel(map, event.reason);
}

export function HistorySheet({ period, date, products, onClose }: HistorySheetProps) {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);
  const [dayFilter, setDayFilter] = useState(date);
  const [events, setEvents] = useState<HistoryEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setEvents(null);
    setError(null);
    api
      .getFinanceHistory(period, dayFilter)
      .then((result) => {
        if (mounted) setEvents(result);
      })
      .catch((err) => {
        if (mounted) setError(errorMessage(err, t("history.loadFailed")));
      });
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t навмисно не в deps: рефетч лише на period/dayFilter
  }, [period, dayFilter]);

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  const sheet = (
    <>
      <div
        className={`sheet-backdrop${isClosing ? " sheet-backdrop--closing" : ""}`}
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-label={t("history.title")}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label">
            {dayFilter ? t("history.titleWithDate", { date: dayFilter }) : t("history.title")}
          </span>
          <button
            type="button"
            className="sheet-close"
            aria-label={t("common.close")}
            onClick={handleClose}
          >
            ✕
          </button>
        </div>

        {dayFilter ? (
          <button
            type="button"
            className="history-clear-day"
            onClick={() => setDayFilter(undefined)}
          >
            {t("history.showAllDates")}
          </button>
        ) : null}

        {error ? <p className="error-banner">{error}</p> : null}

        {events === null ? (
          <p className="status-text">{t("common.loading")}</p>
        ) : events.length === 0 ? (
          <p className="status-text">{t("history.empty")}</p>
        ) : (
          <ul className="history-list">
            {events.map((event) => {
              const reasonKey = eventReasonLabel(event);
              const metaParts = [
                event.amount ? `${event.amount} ₴` : null,
                reasonKey ? t(reasonKey) : null,
                event.customer,
              ].filter((part): part is string => Boolean(part));

              const product = products.find((p) => p.name === event.product_name);
              const { photoUrl, letter } = resolveProductPhoto(product, event.product_name);
              const badge = EVENT_BADGE[event.type];

              return (
                <li key={event.id} className="history-row">
                  {photoUrl ? (
                    <img src={photoUrl} alt="" className="history-row-photo" />
                  ) : (
                    <span className="history-row-photo history-row-photo--neutral">{letter}</span>
                  )}
                  <div className="history-row-center">
                    <div className="history-row-top">
                      <span className="history-row-title">
                        {event.product_name}
                        {event.variant_label ? ` · ${event.variant_label}` : ""} · {event.qty}{" "}
                        {t("history.unitsShort")}
                      </span>
                      <span className={`badge ${badge.className}`}>{t(badge.labelKey)}</span>
                    </div>
                    {metaParts.length > 0 ? (
                      <span className="history-row-meta">{metaParts.join(" · ")}</span>
                    ) : null}
                    <span className="history-row-meta">{formatEventDate(event.date)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
