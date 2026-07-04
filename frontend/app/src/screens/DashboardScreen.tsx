import type { RefObject } from "react";
import type { MetricCardData } from "../components/MetricCarousel";
import { MetricCarousel } from "../components/MetricCarousel";
import { ReservationsPanel } from "../components/ReservationsPanel";
import { ScrollFloat } from "../components/ScrollFloat";
import { Panel } from "../components/ui/Panel";
import type {
  FinanceSummary,
  NotPickedUpPayload,
  Product,
  ReleasePayload,
  Reservation,
  ShipPayload,
  Shop,
  Variant,
} from "../types";

interface DashboardScreenProps {
  shop: Shop | null;
  loading: boolean;
  finance: FinanceSummary;
  metricCards: MetricCardData[];
  reservations: Reservation[];
  resolveReservationVariant: (variantId: number) => { variant: Variant; product: Product } | null;
  onRelease: (id: number, payload?: ReleasePayload) => Promise<void>;
  onFulfill: (id: number) => Promise<void>;
  onShip: (id: number, payload: ShipPayload) => Promise<void>;
  onUpdateTtn: (id: number, ttn: string) => Promise<void>;
  onPickUp: (id: number) => Promise<void>;
  onNotPickedUp: (id: number, payload: NotPickedUpPayload) => Promise<void>;
  onNavigateToSklad: () => void;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

export function DashboardScreen({
  shop,
  loading,
  finance,
  metricCards,
  reservations,
  resolveReservationVariant,
  onRelease,
  onFulfill,
  onShip,
  onUpdateTtn,
  onPickUp,
  onNotPickedUp,
  onNavigateToSklad,
  scrollContainerRef,
}: DashboardScreenProps) {
  return (
    <>
      {shop ? <MetricCarousel cards={metricCards} onNavigate={onNavigateToSklad} /> : null}

      <div className="glass-card rounded-[20px] p-4 mb-4 shadow-[var(--shadow-card)]">
        <h2 className="section-title mb-2">Фінанси</h2>
        <div className="finance-row">
          <span className="text-sm text-text-soft">Дохід</span>
          <span className="font-mono-price text-base font-semibold text-text">
            {Number(finance.revenue_uah || "0").toLocaleString("uk-UA", {
              style: "currency",
              currency: "UAH",
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
        <div className="finance-row">
          <span className="text-sm text-text-soft">Продажів</span>
          <span className="font-mono-price text-base font-semibold text-text">
            {finance.sales_count || 0}
          </span>
        </div>
        <div className="finance-row finance-row--last">
          <span className="text-sm text-text-soft">Одиниць продано</span>
          <span className="font-mono-price text-base font-semibold text-text">
            {finance.units_sold || 0}
          </span>
        </div>
        <p className="text-xs text-text-soft mt-2">
          Дохід рахується з продажів (швидке списання «Продано» та виконані резерви)
        </p>
      </div>

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
              resolveReservationVariant={resolveReservationVariant}
              onRelease={onRelease}
              onFulfill={onFulfill}
              onShip={onShip}
              onUpdateTtn={onUpdateTtn}
              onPickUp={onPickUp}
              onNotPickedUp={onNotPickedUp}
            />
          )}
        </div>
      </Panel>
    </>
  );
}
