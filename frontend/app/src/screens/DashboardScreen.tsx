import { useEffect, useState } from "react";
import type { RefObject } from "react";
import * as api from "../api";
import type { MetricCardData } from "../components/MetricCarousel";
import { MetricCarousel } from "../components/MetricCarousel";
import { ReservationsPanel } from "../components/ReservationsPanel";
import { ScrollFloat } from "../components/ScrollFloat";
import { Panel } from "../components/ui/Panel";
import type { FinanceSummary, Reservation, Shop } from "../types";

interface DashboardScreenProps {
  shop: Shop | null;
  loading: boolean;
  metricCards: MetricCardData[];
  reservations: Reservation[];
  writable: boolean;
  variantLabel: (variantId: number) => string;
  onRelease: (id: number) => Promise<void>;
  onFulfill: (id: number) => Promise<void>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

export function DashboardScreen({
  shop,
  loading,
  metricCards,
  reservations,
  writable,
  variantLabel,
  onRelease,
  onFulfill,
  scrollContainerRef,
}: DashboardScreenProps) {
  const [finance, setFinance] = useState<FinanceSummary | null>(null);

  useEffect(() => {
    if (shop?.role !== "owner") return;
    let cancelled = false;
    api
      .getFinanceSummary()
      .then((data) => {
        if (!cancelled) setFinance(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) console.error("[DashboardScreen] finance fetch failed:", err);
      });
    return () => {
      cancelled = true;
    };
  }, [shop?.role]);

  return (
    <>
      {shop ? <MetricCarousel cards={metricCards} /> : null}

      {finance ? (
        <div className="glass-card rounded-[20px] p-4 mb-4 shadow-[var(--shadow-card)]">
          <h2 className="section-title mb-2">Фінанси</h2>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-soft">Дохід</span>
            <span className="font-mono-price text-base font-semibold text-text">
              {Number(finance.revenue_uah).toLocaleString("uk-UA", {
                style: "currency",
                currency: "UAH",
                maximumFractionDigits: 2,
              })}
            </span>
          </div>
        </div>
      ) : null}

      <Panel as="section" className="reservations-section p-0">
        <ScrollFloat
          as="h2"
          className="section-title px-4 pt-4"
          scrollContainerRef={scrollContainerRef}
        >
          Резерви
        </ScrollFloat>
        <div className="px-4 pb-4">
          {loading ? (
            <p className="status-text">Завантаження…</p>
          ) : (
            <ReservationsPanel
              reservations={reservations}
              writable={writable}
              variantLabel={variantLabel}
              onRelease={onRelease}
              onFulfill={onFulfill}
            />
          )}
        </div>
      </Panel>
    </>
  );
}
