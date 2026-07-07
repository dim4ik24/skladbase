import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import * as api from "../api";
import { errorMessage } from "../errors";
import { RELEASE_REASON_LABELS, RETURN_REASON_LABELS, reasonLabel } from "../lib/financeReasons";
import type { FinancePeriod, HistoryEvent } from "../types";

interface HistorySheetProps {
  period: FinancePeriod;
  date?: string;
  onClose: () => void;
}

function formatEventDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${min}`;
}

function eventIcon(type: HistoryEvent["type"]): string {
  if (type === "sale") return "💰";
  if (type === "return") return "↩️";
  return "✖";
}

function eventReasonLabel(event: HistoryEvent): string | null {
  if (!event.reason) return null;
  const map = event.type === "return" ? RETURN_REASON_LABELS : RELEASE_REASON_LABELS;
  return reasonLabel(map, event.reason);
}

export function HistorySheet({ period, date, onClose }: HistorySheetProps) {
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
        if (mounted) setError(errorMessage(err, "Не вдалося завантажити історію"));
      });
    return () => {
      mounted = false;
    };
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
        aria-label="Історія"
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label">Історія{dayFilter ? ` · ${dayFilter}` : ""}</span>
          <button type="button" className="sheet-close" aria-label="Закрити" onClick={handleClose}>
            ✕
          </button>
        </div>

        {dayFilter ? (
          <button
            type="button"
            className="history-clear-day"
            onClick={() => setDayFilter(undefined)}
          >
            Показати всі дати
          </button>
        ) : null}

        {error ? <p className="error-banner">{error}</p> : null}

        {events === null ? (
          <p className="status-text">Завантаження…</p>
        ) : events.length === 0 ? (
          <p className="status-text">Немає подій</p>
        ) : (
          <ul className="history-list">
            {events.map((event) => {
              const metaParts = [
                event.amount ? `${event.amount} ₴` : null,
                eventReasonLabel(event),
                event.customer,
              ].filter((part): part is string => Boolean(part));

              return (
                <li key={event.id} className="history-row">
                  <span className="history-row-icon" aria-hidden="true">
                    {eventIcon(event.type)}
                  </span>
                  <div className="history-row-center">
                    <span className="history-row-title">
                      {event.product_name}
                      {event.variant_label ? ` · ${event.variant_label}` : ""} · {event.qty} шт
                    </span>
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
