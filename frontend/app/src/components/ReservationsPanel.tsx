import { useState } from "react";
import { ReleaseForm } from "./ReleaseForm";
import type { Product, ReleasePayload, Reservation, Variant } from "../types";

interface ReservationsPanelProps {
  reservations: Reservation[];
  resolveReservationVariant: (variantId: number) => { variant: Variant; product: Product } | null;
  onRelease: (reservationId: number, payload?: ReleasePayload) => Promise<void>;
  onFulfill: (reservationId: number) => Promise<void>;
}

function formatCompactDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${min}`;
}

export function ReservationsPanel({
  reservations,
  resolveReservationVariant,
  onRelease,
  onFulfill,
}: ReservationsPanelProps) {
  const [releasingId, setReleasingId] = useState<number | null>(null);

  if (reservations.length === 0) {
    return <p className="status-text">Активних резервів немає</p>;
  }

  async function handleReleaseSubmit(reservationId: number, payload: ReleasePayload) {
    await onRelease(reservationId, payload);
    setReleasingId(null);
  }

  return (
    <ul className="reservation-list">
      {reservations.map((reservation) => {
        const resolved = resolveReservationVariant(reservation.variant_id);
        const variant = resolved?.variant;
        const product = resolved?.product;
        const axisLabel = variant
          ? Object.values(variant.axis_values).filter(Boolean).join(" / ")
          : "";
        const title = product
          ? axisLabel
            ? `${product.name} (${axisLabel})`
            : product.name
          : `Варіант #${reservation.variant_id}`;
        const photoUrl = variant?.photo_url ?? product?.photos[0]?.url ?? null;
        const letter = (axisLabel.charAt(0) || product?.name.charAt(0) || "?").toUpperCase();

        const metaParts = [
          `${reservation.qty} шт.`,
          reservation.customer_note,
          reservation.expires_at ? `до ${formatCompactDate(reservation.expires_at)}` : null,
        ].filter((part): part is string => Boolean(part));

        return (
          <li className="reservation-card" key={reservation.id}>
            {photoUrl ? (
              <img src={photoUrl} alt="" className="reservation-card-chip" />
            ) : (
              <span className="reservation-card-chip reservation-card-chip--neutral">
                {letter}
              </span>
            )}

            <div className="reservation-card-center">
              <span className="reservation-card-title">{title}</span>
              <span className="reservation-card-meta">{metaParts.join(" · ")}</span>
              {releasingId === reservation.id ? (
                <ReleaseForm
                  reservationId={reservation.id}
                  onSubmit={handleReleaseSubmit}
                  onCancel={() => setReleasingId(null)}
                />
              ) : null}
            </div>

            <div className="modal-actions reservation-card-actions">
              <button
                type="button"
                onClick={() =>
                  setReleasingId((prev) => (prev === reservation.id ? null : reservation.id))
                }
              >
                Зняти
              </button>
              <button type="button" onClick={() => onFulfill(reservation.id)}>
                Продано
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
