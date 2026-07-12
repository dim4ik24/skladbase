import { Suspense, useState } from "react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { LazySheetFallback } from "../components/LazyFallback";
import type { MetricCardData } from "../components/MetricCarousel";
import { MetricCarousel } from "../components/MetricCarousel";
import { ReservationsPanel } from "../components/ReservationsPanel";
import { RevenueChart } from "../components/RevenueChart";
import { ScrollFloat } from "../components/ScrollFloat";
import { Panel } from "../components/ui/Panel";
import { RELEASE_REASON_LABELS, RETURN_REASON_LABELS, reasonLabel } from "../lib/financeReasons";
import { lazyWithRetry } from "../lib/lazyWithRetry";
import { resolveProductPhoto } from "../lib/productPhoto";
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

const HistorySheet = lazyWithRetry(() =>
  import("../components/HistorySheet").then((m) => ({ default: m.HistorySheet })),
);

const PERIOD_OPTIONS: { value: FinancePeriod; labelKey: string }[] = [
  { value: "week", labelKey: "finance.period.week" },
  { value: "month", labelKey: "finance.period.month" },
  { value: "year", labelKey: "finance.period.year" },
  { value: "all", labelKey: "finance.period.all" },
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
  products: Product[];
  onOpenProduct: (productId: number) => void;
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
  products,
  onOpenProduct,
}: DashboardScreenProps) {
  const { t } = useTranslation();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyDate, setHistoryDate] = useState<string | undefined>(undefined);

  function openHistory(date?: string) {
    setHistoryDate(date);
    setHistoryOpen(true);
  }

  return (
    <>
      {shop ? <MetricCarousel cards={metricCards} onNavigate={onNavigateToSklad} /> : null}

      <div className="glass-card rounded-[20px] p-4 mb-4 shadow-[var(--shadow-card)]">
        <div className="flex items-center justify-between mb-2">
          <h2 className="section-title mb-0">{t("finance.title")}</h2>
          <button
            type="button"
            className="finance-history-btn"
            onClick={() => openHistory(undefined)}
          >
            {t("finance.historyButton")}
          </button>
        </div>

        <div className="finance-period-chips" role="group" aria-label={t("finance.periodAriaLabel")}>
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
              {t(option.labelKey)}
            </button>
          ))}
        </div>

        {finance.sales_count === 0 ? (
          <p className="status-text finance-empty-state">{t("finance.emptyState")}</p>
        ) : (
          <>
            <RevenueChart
              period={financePeriod}
              chart={finance.chart}
              onOpenHistory={openHistory}
            />

            <div className="finance-row">
              <span className="text-sm text-text-soft">{t("finance.revenue")}</span>
              <span className="font-mono-price text-base font-semibold text-text">
                {formatUah(finance.revenue_uah)}
              </span>
            </div>
            <div className="finance-row finance-row--last">
              <span className="text-sm text-text-soft">{t("finance.salesUnits")}</span>
              <span className="font-mono-price text-base font-semibold text-text">
                {finance.sales_count} · {finance.units_sold}
              </span>
            </div>

            {finance.returns_count > 0 ? (
              <div className="finance-row finance-row--last">
                <span className="text-sm text-text-soft">{t("finance.returns")}</span>
                <span className="finance-returns-value">
                  {formatUah(finance.returns_uah)} · {finance.returns_count}
                </span>
              </div>
            ) : null}
          </>
        )}

        {finance.release_reasons.length > 0 ? (
          <div className="finance-reason-block">
            <h3 className="finance-subsection-title">{t("finance.releaseReasonsTitle")}</h3>
            <ul>
              {finance.release_reasons.map((row) => (
                <li key={row.reason}>
                  {t(reasonLabel(RELEASE_REASON_LABELS, row.reason))} — {row.count}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {finance.return_reasons.length > 0 ? (
          <div className="finance-reason-block">
            <h3 className="finance-subsection-title">{t("finance.returns")}</h3>
            <ul>
              {finance.return_reasons.map((row) => (
                <li key={row.reason}>
                  {t(reasonLabel(RETURN_REASON_LABELS, row.reason))} — {row.count}
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
          {t("reservations.title")}
        </ScrollFloat>
        <div className="px-4 pb-4">
          {loading ? (
            <p className="status-text">{t("common.loading")}</p>
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

      {finance.top_products.length > 0 ? (
        <div className="glass-card rounded-[20px] p-4 mb-4 shadow-[var(--shadow-card)]">
          <h2 className="section-title mb-2">{t("finance.topProductsTitle")}</h2>
          <div className="finance-top-products">
            <ul>
              {finance.top_products.map((topProduct) => {
                const product = products.find((p) => p.id === topProduct.product_id);
                const { photoUrl, letter } = resolveProductPhoto(product, topProduct.name);
                return (
                  <li
                    key={topProduct.product_id}
                    role={product ? "button" : undefined}
                    tabIndex={product ? 0 : undefined}
                    onClick={product ? () => onOpenProduct(topProduct.product_id) : undefined}
                    className={`finance-top-product-row${
                      product ? " finance-top-product-row--clickable" : ""
                    }`}
                  >
                    {photoUrl ? (
                      <img src={photoUrl} alt="" className="finance-top-product-photo" />
                    ) : (
                      <span className="finance-top-product-photo finance-top-product-photo--neutral">
                        {letter}
                      </span>
                    )}
                    <span className="finance-top-product-name">{topProduct.name}</span>
                    <span className="finance-top-product-value">
                      {t("finance.topProductLine", {
                        revenue: formatUah(topProduct.revenue_uah),
                        units: topProduct.units,
                      })}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      ) : null}

      {historyOpen ? (
        <Suspense fallback={<LazySheetFallback />}>
          <HistorySheet
            period={financePeriod}
            date={historyDate}
            products={products}
            onClose={() => setHistoryOpen(false)}
          />
        </Suspense>
      ) : null}
    </>
  );
}
