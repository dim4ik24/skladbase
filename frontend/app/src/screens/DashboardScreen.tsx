import type { RefObject } from "react";
import type { MetricCardData } from "../components/MetricCarousel";
import { MetricCarousel } from "../components/MetricCarousel";
import { ReservationsPanel } from "../components/ReservationsPanel";
import { RevenueChart } from "../components/RevenueChart";
import { ScrollFloat } from "../components/ScrollFloat";
import { Panel } from "../components/ui/Panel";
import { RELEASE_REASON_LABELS, RETURN_REASON_LABELS, reasonLabel } from "../lib/financeReasons";
import type {
  CreateTtnPayload,
  CreateTtnResult,
  FinancePeriod,
  FinanceSummary,
  NotPickedUpPayload,
  Product,
  ReleasePayload,
  Reservation,
  ShipPayload,
  Shop,
  Variant,
} from "../types";

const PERIOD_OPTIONS: { value: FinancePeriod; label: string }[] = [
  { value: "week", label: "Тиждень" },
  { value: "month", label: "Місяць" },
  { value: "year", label: "Рік" },
  { value: "all", label: "Весь час" },
];

function formatUah(value: string | number): string {
  return Number(value || 0).toLocaleString("uk-UA", {
    style: "currency",
    currency: "UAH",
    maximumFractionDigits: 2,
  });
}

interface DashboardScreenProps {
  shop: Shop | null;
  loading: boolean;
  finance: FinanceSummary;
  financePeriod: FinancePeriod;
  onFinancePeriodChange: (period: FinancePeriod) => void;
  metricCards: MetricCardData[];
  reservations: Reservation[];
  resolveReservationVariant: (variantId: number) => { variant: Variant; product: Product } | null;
  onRelease: (id: number, payload?: ReleasePayload) => Promise<void>;
  onFulfill: (id: number) => Promise<void>;
  onShip: (id: number, payload: ShipPayload) => Promise<void>;
  onUpdateTtn: (id: number, ttn: string) => Promise<void>;
  onPickUp: (id: number) => Promise<void>;
  onNotPickedUp: (id: number, payload: NotPickedUpPayload) => Promise<void>;
  onCreateTtn: (id: number, payload: CreateTtnPayload) => Promise<CreateTtnResult>;
  onNavigateToSettings: () => void;
  onNavigateToSklad: () => void;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

export function DashboardScreen({
  shop,
  loading,
  finance,
  financePeriod,
  onFinancePeriodChange,
  metricCards,
  reservations,
  resolveReservationVariant,
  onRelease,
  onFulfill,
  onShip,
  onUpdateTtn,
  onPickUp,
  onNotPickedUp,
  onCreateTtn,
  onNavigateToSettings,
  onNavigateToSklad,
  scrollContainerRef,
}: DashboardScreenProps) {
  return (
    <>
      {shop ? <MetricCarousel cards={metricCards} onNavigate={onNavigateToSklad} /> : null}

      <div className="glass-card rounded-[20px] p-4 mb-4 shadow-[var(--shadow-card)]">
        <h2 className="section-title mb-2">Фінанси</h2>

        <div className="finance-period-chips" role="group" aria-label="Період">
          {PERIOD_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`finance-period-chip${
                financePeriod === option.value ? " finance-period-chip--active" : ""
              }`}
              aria-pressed={financePeriod === option.value}
              onClick={() => onFinancePeriodChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>

        {finance.sales_count === 0 ? (
          <p className="status-text finance-empty-state">Немає продажів за цей період</p>
        ) : (
          <>
            <RevenueChart period={financePeriod} chart={finance.chart} />

            <div className="finance-row">
              <span className="text-sm text-text-soft">Дохід</span>
              <span className="font-mono-price text-base font-semibold text-text">
                {formatUah(finance.revenue_uah)}
              </span>
            </div>
            <div className="finance-row finance-row--last">
              <span className="text-sm text-text-soft">Продажів · Одиниць</span>
              <span className="font-mono-price text-base font-semibold text-text">
                {finance.sales_count} · {finance.units_sold}
              </span>
            </div>

            {finance.returns_count > 0 ? (
              <div className="finance-row finance-row--last">
                <span className="text-sm text-text-soft">Повернення</span>
                <span className="finance-returns-value">
                  {formatUah(finance.returns_uah)} · {finance.returns_count}
                </span>
              </div>
            ) : null}

            {finance.top_products.length > 0 ? (
              <div className="finance-top-products">
                <h3 className="finance-subsection-title">Топ товарів</h3>
                <ul>
                  {finance.top_products.map((product) => (
                    <li key={product.product_id} className="finance-top-product-row">
                      <span className="finance-top-product-name">{product.name}</span>
                      <span className="finance-top-product-value">
                        {formatUah(product.revenue_uah)} · {product.units} шт.
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}

        {finance.release_reasons.length > 0 ? (
          <div className="finance-reason-block">
            <h3 className="finance-subsection-title">Зняття резервів</h3>
            <ul>
              {finance.release_reasons.map((row) => (
                <li key={row.reason}>
                  {reasonLabel(RELEASE_REASON_LABELS, row.reason)} — {row.count}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {finance.return_reasons.length > 0 ? (
          <div className="finance-reason-block">
            <h3 className="finance-subsection-title">Повернення</h3>
            <ul>
              {finance.return_reasons.map((row) => (
                <li key={row.reason}>
                  {reasonLabel(RETURN_REASON_LABELS, row.reason)} — {row.count}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
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
              onCreateTtn={onCreateTtn}
              onNavigateToSettings={onNavigateToSettings}
            />
          )}
        </div>
      </Panel>
    </>
  );
}
