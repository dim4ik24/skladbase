import { useState } from "react";
import { NotPickedUpSheet } from "./NotPickedUpSheet";
import { ReleaseSheet } from "./ReleaseSheet";
import { ShipSheet } from "./ShipSheet";
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
  const [releasingId, setReleasingId] = useState<number | null>(null);
  const [shippingId, setShippingId] = useState<number | null>(null);
  const [notPickedUpId, setNotPickedUpId] = useState<number | null>(null);
  const [editingTtnId, setEditingTtnId] = useState<number | null>(null);
  const [ttnDraft, setTtnDraft] = useState("");

  if (reservations.length === 0) {
    return <p className="status-text">Активних резервів немає</p>;
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

  async function handleTtnSave(reservationId: number) {
    const trimmed = ttnDraft.trim();
    if (trimmed) {
      await onUpdateTtn(reservationId, trimmed);
    }
    setEditingTtnId(null);
  }

  const releasingReservation = reservations.find((r) => r.id === releasingId) ?? null;
  const shippingReservation = reservations.find((r) => r.id === shippingId) ?? null;
  const notPickedUpReservation = reservations.find((r) => r.id === notPickedUpId) ?? null;

  function resolveShipDefaults(reservation: Reservation): {
    productName: string;
    defaultCodAmount: number;
  } {
    const resolved = resolveReservationVariant(reservation.variant_id);
    return {
      productName: resolved?.product.name ?? `Варіант #${reservation.variant_id}`,
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
    const name = product ? product.name : `Варіант #${reservation.variant_id}`;
    const inner = [axisLabel, `${reservation.qty} шт.`].filter(Boolean).join(", ");
    return `${name} (${inner})`;
  }

  return (
    <>
      <ul className="reservation-list">
        {reservations.map((reservation) => {
          // Fallback навмисно не порожній: якщо variant/product ще не
          // прийшли (products не завантажені/варіант видалили) — бирка
          // все одно показує номер резерву і кількість, а не порожнечу.
          const resolved = resolveReservationVariant(reservation.variant_id);
          const variant = resolved?.variant;
          const product = resolved?.product;
          const axisLabel = variant
            ? Object.values(variant.axis_values).filter(Boolean).join(" / ")
            : "";
          const title = product ? product.name : `Варіант #${reservation.variant_id}`;
          const photoUrl = variant?.photo_url ?? product?.photos[0]?.url ?? null;
          const letter = (axisLabel.charAt(0) || product?.name.charAt(0) || "?").toUpperCase();

          const qtyPriceLine = variant
            ? `${reservation.qty} шт. × ${fmtMoney(Number(variant.price))} ₴ = ${fmtMoney(
                Number(variant.price) * reservation.qty,
              )} ₴`
            : `${reservation.qty} шт.`;
          const row2 = [axisLabel, qtyPriceLine].filter(Boolean).join(" · ");

          const isShipped = reservation.status === "shipped";
          const isEditingTtn = editingTtnId === reservation.id;

          const row3Parts = [
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
                <span className="reservation-card-meta">{row2}</span>
                {row3Parts.length > 0 ? (
                  <span className="reservation-card-meta">{row3Parts.join(" · ")}</span>
                ) : null}
                {isShipped ? (
                  isEditingTtn ? (
                    <span className="reservation-card-meta reservation-ttn-edit">
                      <input
                        type="text"
                        value={ttnDraft}
                        autoFocus
                        onChange={(event) => setTtnDraft(event.target.value)}
                        onBlur={() => void handleTtnSave(reservation.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void handleTtnSave(reservation.id);
                        }}
                      />
                    </span>
                  ) : (
                    <span
                      className="reservation-card-meta reservation-ttn-tap"
                      onClick={() => {
                        setEditingTtnId(reservation.id);
                        setTtnDraft(reservation.ttn ?? "");
                      }}
                    >
                      🚚 {reservation.ttn ? reservation.ttn : "Відправлено (додати ТТН)"}
                    </span>
                  )
                ) : null}
                {isShipped && reservation.np_status ? (
                  <span className="reservation-card-meta">📍 {reservation.np_status}</span>
                ) : null}
              </div>

              <div className="modal-actions reservation-card-actions">
                {reservation.status === "active" ? (
                  <>
                    <button type="button" onClick={() => setReleasingId(reservation.id)}>
                      Зняти
                    </button>
                    <button type="button" onClick={() => setShippingId(reservation.id)}>
                      Відправлено
                    </button>
                    <button type="button" onClick={() => onFulfill(reservation.id)}>
                      Продано
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={() => setNotPickedUpId(reservation.id)}>
                      Не забрав
                    </button>
                    <button type="button" onClick={() => onPickUp(reservation.id)}>
                      Забрав
                    </button>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {releasingReservation ? (
        <ReleaseSheet
          reservationId={releasingReservation.id}
          title={resolveTitle(releasingReservation)}
          onSubmit={handleReleaseSubmit}
          onClose={() => setReleasingId(null)}
        />
      ) : null}

      {shippingReservation ? (
        <ShipSheet
          reservationId={shippingReservation.id}
          title={resolveTitle(shippingReservation)}
          {...resolveShipDefaults(shippingReservation)}
          onSubmit={handleShipSubmit}
          onCreateTtn={onCreateTtn}
          onNavigateToSettings={onNavigateToSettings}
          onClose={() => setShippingId(null)}
        />
      ) : null}

      {notPickedUpReservation ? (
        <NotPickedUpSheet
          reservationId={notPickedUpReservation.id}
          title={resolveTitle(notPickedUpReservation)}
          onSubmit={handleNotPickedUpSubmit}
          onClose={() => setNotPickedUpId(null)}
        />
      ) : null}
    </>
  );
}
