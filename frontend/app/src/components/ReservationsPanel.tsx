import { Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { lazyWithRetry } from "../lib/lazyWithRetry";
import { ReservationSheet } from "./ReservationSheet";
import type {
  CreateTtnPayload,
  CreateTtnResult,
  NotPickedUpPayload,
  Product,
  ReleasePayload,
  Reservation,
  ShipPayload,
  Variant,
} from "../types";
import { LazySheetFallback } from "./LazyFallback";

const ReleaseSheet = lazyWithRetry(() =>
  import("./ReleaseSheet").then((m) => ({ default: m.ReleaseSheet })),
);
const ShipSheet = lazyWithRetry(() =>
  import("./ShipSheet").then((m) => ({ default: m.ShipSheet })),
);
const NotPickedUpSheet = lazyWithRetry(() =>
  import("./NotPickedUpSheet").then((m) => ({ default: m.NotPickedUpSheet })),
);

interface ReservationsPanelProps {
  reservations: Reservation[];
  resolveReservationVariant: (variantId: number) => { variant: Variant; product: Product } | null;
  onRelease: (reservationId: number, payload?: ReleasePayload) => Promise<void>;
  onFulfill: (reservationId: number) => Promise<void>;
  onShip: (reservationId: number, payload: ShipPayload) => Promise<void>;
  onUpdateTtn: (reservationId: number, ttn: string) => Promise<void>;
  onPickUp: (reservationId: number) => Promise<void>;
  onNotPickedUp: (reservationId: number, payload: NotPickedUpPayload) => Promise<void>;
  onCreateTtn: (reservationId: number, payload: CreateTtnPayload) => Promise<CreateTtnResult>;
  onNavigateToSettings: () => void;
}

function formatCompactDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${min}`;
}

function fmtMoney(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function ReservationsPanel({
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
}: ReservationsPanelProps) {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [releasingId, setReleasingId] = useState<number | null>(null);
  const [shippingId, setShippingId] = useState<number | null>(null);
  const [notPickedUpId, setNotPickedUpId] = useState<number | null>(null);

  if (reservations.length === 0) {
    return <p className="status-text">{t("reservations.empty")}</p>;
  }

  async function handleReleaseSubmit(reservationId: number, payload: ReleasePayload) {
    await onRelease(reservationId, payload);
    setReleasingId(null);
  }

  async function handleShipSubmit(reservationId: number, payload: ShipPayload) {
    await onShip(reservationId, payload);
    setShippingId(null);
  }

  async function handleNotPickedUpSubmit(reservationId: number, payload: NotPickedUpPayload) {
    await onNotPickedUp(reservationId, payload);
    setNotPickedUpId(null);
  }

  const activeReservation = reservations.find((r) => r.id === activeId) ?? null;
  const releasingReservation = reservations.find((r) => r.id === releasingId) ?? null;
  const shippingReservation = reservations.find((r) => r.id === shippingId) ?? null;
  const notPickedUpReservation = reservations.find((r) => r.id === notPickedUpId) ?? null;

  function resolveShipDefaults(reservation: Reservation): {
    productName: string;
    defaultCodAmount: number;
  } {
    const resolved = resolveReservationVariant(reservation.variant_id);
    return {
      productName:
        resolved?.product.name ?? t("reservations.variantFallback", { id: reservation.variant_id }),
      defaultCodAmount: resolved ? Number(resolved.variant.price) * reservation.qty : 0,
    };
  }

  function resolveTitle(reservation: Reservation): string {
    const resolved = resolveReservationVariant(reservation.variant_id);
    const variant = resolved?.variant;
    const product = resolved?.product;
    const axisLabel = variant
      ? Object.values(variant.axis_values).filter(Boolean).join(" / ")
      : "";
    const name = product ? product.name : t("reservations.variantFallback", { id: reservation.variant_id });
    const inner = [axisLabel, `${reservation.qty} ${t("common.unitsShort")}`]
      .filter(Boolean)
      .join(", ");
    return `${name} (${inner})`;
  }

  function resolveDisplay(reservation: Reservation) {
    const resolved = resolveReservationVariant(reservation.variant_id);
    const variant = resolved?.variant;
    const product = resolved?.product;
    const axisLabel = variant
      ? Object.values(variant.axis_values).filter(Boolean).join(" / ")
      : "";
    const title = product
      ? product.name
      : t("reservations.variantFallback", { id: reservation.variant_id });
    const photoUrl = variant?.photo_url ?? product?.photos[0]?.url ?? null;
    const letter = (axisLabel.charAt(0) || product?.name.charAt(0) || "?").toUpperCase();
    const unitPrice = variant ? Number(variant.price) : null;
    const sum = variant ? Number(variant.price) * reservation.qty : null;
    const deadlineLabel = reservation.expires_at
      ? formatCompactDate(reservation.expires_at)
      : null;
    return { axisLabel, title, photoUrl, letter, unitPrice, sum, deadlineLabel };
  }

  return (
    <>
      <ul className="reservation-list">
        {reservations.map((reservation) => {
          // Fallback навмисно не порожній: якщо variant/product ще не
          // прийшли (products не завантажені/варіант видалили) — бирка
          // все одно показує номер резерву і кількість, а не порожнечу.
          const { axisLabel, title, photoUrl, letter, unitPrice, sum } =
            resolveDisplay(reservation);

          const qtyPriceLine =
            unitPrice !== null && sum !== null
              ? t("reservations.qtyPriceLine", {
                  qty: reservation.qty,
                  unitPrice: fmtMoney(unitPrice),
                  sum: fmtMoney(sum),
                })
              : `${reservation.qty} ${t("common.unitsShort")}`;
          const row2 = [axisLabel, qtyPriceLine].filter(Boolean).join(" · ");

          const isShipped = reservation.status === "shipped";

          const row3Parts = [
            reservation.customer_note,
            reservation.expires_at
              ? t("reservations.until", { date: formatCompactDate(reservation.expires_at) })
              : null,
          ].filter((part): part is string => Boolean(part));

          return (
            <li key={reservation.id}>
              <button
                type="button"
                className="reservation-card"
                aria-label={t("reservations.cardAriaLabel", { title })}
                onClick={() => setActiveId(reservation.id)}
              >
                {photoUrl ? (
                  <img src={photoUrl} alt="" className="reservation-card-chip" />
                ) : (
                  <span className="reservation-card-chip reservation-card-chip--neutral">
                    {letter}
                  </span>
                )}

                <div className="reservation-card-center">
                  <span className="reservation-card-title">{title}</span>
                  <span className="reservation-card-meta">{row2}</span>
                  {row3Parts.length > 0 ? (
                    <span className="reservation-card-meta">{row3Parts.join(" · ")}</span>
                  ) : null}
                  {isShipped ? (
                    <span className="reservation-card-meta">
                      🚚 {reservation.ttn ? reservation.ttn : t("reservations.shippedNoTtn")}
                    </span>
                  ) : null}
                  {isShipped && reservation.np_status ? (
                    <span className="reservation-card-meta">📍 {reservation.np_status}</span>
                  ) : null}
                </div>

                <span className="reservation-card-right">
                  <span className={`badge${isShipped ? " badge-shipped" : " badge-active"}`}>
                    {isShipped ? t("reservations.badgeShipped") : t("reservations.badgeActive")}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {activeReservation ? (
        <ReservationSheet
          reservation={activeReservation}
          {...resolveDisplay(activeReservation)}
          title={resolveDisplay(activeReservation).title}
          qty={activeReservation.qty}
          customerNote={activeReservation.customer_note}
          onRequestRelease={() => setReleasingId(activeReservation.id)}
          onRequestShip={() => setShippingId(activeReservation.id)}
          onRequestNotPickedUp={() => setNotPickedUpId(activeReservation.id)}
          onFulfill={onFulfill}
          onPickUp={onPickUp}
          onUpdateTtn={onUpdateTtn}
          onClose={() => setActiveId(null)}
        />
      ) : null}

      {releasingReservation ? (
        <Suspense fallback={<LazySheetFallback />}>
          <ReleaseSheet
            reservationId={releasingReservation.id}
            title={resolveTitle(releasingReservation)}
            onSubmit={handleReleaseSubmit}
            onClose={() => setReleasingId(null)}
          />
        </Suspense>
      ) : null}

      {shippingReservation ? (
        <Suspense fallback={<LazySheetFallback />}>
          <ShipSheet
            reservationId={shippingReservation.id}
            title={resolveTitle(shippingReservation)}
            {...resolveShipDefaults(shippingReservation)}
            onSubmit={handleShipSubmit}
            onCreateTtn={onCreateTtn}
            onNavigateToSettings={onNavigateToSettings}
            onClose={() => setShippingId(null)}
          />
        </Suspense>
      ) : null}

      {notPickedUpReservation ? (
        <Suspense fallback={<LazySheetFallback />}>
          <NotPickedUpSheet
            reservationId={notPickedUpReservation.id}
            title={resolveTitle(notPickedUpReservation)}
            onSubmit={handleNotPickedUpSubmit}
            onClose={() => setNotPickedUpId(null)}
          />
        </Suspense>
      ) : null}
    </>
  );
}
