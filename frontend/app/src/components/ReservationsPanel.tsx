import type { Reservation } from "../types";

interface ReservationsPanelProps {
  reservations: Reservation[];
  writable: boolean;
  variantLabel: (variantId: number) => string;
  onRelease: (reservationId: number) => void;
  onFulfill: (reservationId: number) => void;
}

export function ReservationsPanel({
  reservations,
  writable,
  variantLabel,
  onRelease,
  onFulfill,
}: ReservationsPanelProps) {
  if (reservations.length === 0) {
    return <p className="status-text">Активних резервів немає</p>;
  }

  return (
    <ul className="reservation-list">
      {reservations.map((reservation) => (
        <li className="reservation-row" key={reservation.id}>
          <div className="reservation-info">
            <span className="reservation-variant">{variantLabel(reservation.variant_id)}</span>
            <span>{reservation.qty} шт.</span>
            {reservation.customer_note ? (
              <span className="variant-axis">{reservation.customer_note}</span>
            ) : null}
            {reservation.expires_at ? (
              <span className="variant-axis">
                до {new Date(reservation.expires_at).toLocaleString()}
              </span>
            ) : null}
          </div>
          <div className="modal-actions">
            <button type="button" disabled={!writable} onClick={() => onRelease(reservation.id)}>
              Зняти
            </button>
            <button type="button" disabled={!writable} onClick={() => onFulfill(reservation.id)}>
              Продано
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
