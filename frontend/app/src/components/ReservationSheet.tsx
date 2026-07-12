import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";
import { isValidTtn } from "../lib/ttn";
import type { Reservation } from "../types";

interface ReservationSheetProps {
  reservation: Reservation;
  title: string;
  axisLabel: string;
  photoUrl: string | null;
  letter: string;
  qty: number;
  unitPrice: number | null;
  sum: number | null;
  customerNote: string | null;
  deadlineLabel: string | null;
  onRequestRelease: () => void;
  onRequestShip: () => void;
  onRequestNotPickedUp: () => void;
  onFulfill: (reservationId: number) => Promise<void>;
  onPickUp: (reservationId: number) => Promise<void>;
  onUpdateTtn: (reservationId: number, ttn: string) => Promise<void>;
  onClose: () => void;
}

function fmtMoney(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function ReservationSheet({
  reservation,
  title,
  axisLabel,
  photoUrl,
  letter,
  qty,
  unitPrice,
  sum,
  customerNote,
  deadlineLabel,
  onRequestRelease,
  onRequestShip,
  onRequestNotPickedUp,
  onFulfill,
  onPickUp,
  onUpdateTtn,
  onClose,
}: ReservationSheetProps) {
  const { t } = useTranslation();
  const [isClosing, setIsClosing] = useState(false);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingTtn, setEditingTtn] = useState(false);
  const [ttnDraft, setTtnDraft] = useState(reservation.ttn ?? "");
  const [ttnError, setTtnError] = useState<string | null>(null);

  const isShipped = reservation.status === "shipped";

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  function requestRelease() {
    onRequestRelease();
    handleClose();
  }

  function requestShip() {
    onRequestShip();
    handleClose();
  }

  function requestNotPickedUp() {
    onRequestNotPickedUp();
    handleClose();
  }

  async function handleFulfill() {
    setActionError(null);
    setActing(true);
    try {
      await onFulfill(reservation.id);
      handleClose();
    } catch (err) {
      setActionError(errorMessage(err, t("reservations.sheet.fulfillFailed")));
      setActing(false);
    }
  }

  async function handlePickUp() {
    setActionError(null);
    setActing(true);
    try {
      await onPickUp(reservation.id);
      handleClose();
    } catch (err) {
      setActionError(errorMessage(err, t("reservations.sheet.pickupFailed")));
      setActing(false);
    }
  }

  async function handleTtnSave() {
    const trimmed = ttnDraft.trim();
    if (trimmed && !isValidTtn(trimmed)) {
      setTtnError(t("shipping.ttnError"));
      return;
    }
    setTtnError(null);
    setEditingTtn(false);
    if (trimmed && trimmed !== reservation.ttn) {
      await onUpdateTtn(reservation.id, trimmed);
    }
  }

  const sheet = (
    <>
      <div
        className={`sheet-backdrop${isClosing ? " sheet-backdrop--closing" : ""}`}
        onClick={handleClose}
      />
      <div
        role="dialog"
        aria-label={t("reservations.cardAriaLabel", { title })}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          {photoUrl ? (
            <img
              src={photoUrl}
              alt=""
              className="variant-chip variant-chip--photo reservation-sheet-photo"
            />
          ) : (
            <span className="variant-chip variant-chip--neutral reservation-sheet-photo">
              {letter}
            </span>
          )}
          <span className="sheet-axis-label release-sheet-title">{title}</span>
          <button
            type="button"
            className="sheet-close"
            aria-label={t("common.close")}
            onClick={handleClose}
          >
            ✕
          </button>
        </div>

        {actionError ? <p className="error-banner">{actionError}</p> : null}

        <div className="reservation-sheet-info">
          {axisLabel ? <p className="reservation-sheet-row">{axisLabel}</p> : null}
          <p className="reservation-sheet-row">
            {qty} {t("common.unitsShort")}
            {unitPrice !== null ? ` × ${fmtMoney(unitPrice)} ₴` : ""}
            {sum !== null ? ` = ${fmtMoney(sum)} ₴` : ""}
          </p>
          {customerNote ? <p className="reservation-sheet-row">{customerNote}</p> : null}
          {deadlineLabel ? (
            <p className="reservation-sheet-row">{t("reservations.until", { date: deadlineLabel })}</p>
          ) : null}

          <span
            className={`badge reservation-status-badge${
              isShipped ? " badge-shipped" : " badge-active"
            }`}
          >
            {isShipped ? t("reservations.badgeShipped") : t("reservations.badgeActive")}
          </span>

          {isShipped ? (
            <p className="reservation-sheet-row reservation-sheet-ttn">
              {editingTtn ? (
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={14}
                  autoFocus
                  value={ttnDraft}
                  onChange={(e) => {
                    setTtnDraft(e.target.value);
                    setTtnError(null);
                  }}
                  onBlur={() => void handleTtnSave()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleTtnSave();
                  }}
                  aria-invalid={ttnError !== null}
                  className={ttnError !== null ? "input-error" : undefined}
                />
              ) : (
                <span
                  className="reservation-ttn-tap"
                  onClick={() => {
                    setEditingTtn(true);
                    setTtnDraft(reservation.ttn ?? "");
                  }}
                >
                  {t("reservations.ttnLabel")} {reservation.ttn ? reservation.ttn : t("reservations.ttnAdd")}
                </span>
              )}
              {reservation.np_status ? <> · 📍 {reservation.np_status}</> : null}
              {reservation.np_recipient ? <> · 📮 {reservation.np_recipient}</> : null}
            </p>
          ) : null}
          {ttnError ? <p className="error-banner">{ttnError}</p> : null}
        </div>

        <div className="sheet-divider" />

        <div className="modal-actions reservation-sheet-actions">
          {reservation.status === "active" ? (
            <>
              <button type="button" onClick={requestShip} disabled={acting}>
                {t("reservations.actions.ship")}
              </button>
              <button type="button" onClick={() => void handleFulfill()} disabled={acting}>
                {acting ? t("common.ellipsis") : t("reservations.actions.sold")}
              </button>
              <button type="button" onClick={requestRelease} disabled={acting}>
                {t("reservations.actions.release")}
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => void handlePickUp()} disabled={acting}>
                {acting ? t("common.ellipsis") : t("reservations.actions.pickedUp")}
              </button>
              <button type="button" onClick={requestNotPickedUp} disabled={acting}>
                {t("reservations.actions.notPickedUp")}
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
