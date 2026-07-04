import { useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";
import type { ShipPayload } from "../types";

interface ShipSheetProps {
  reservationId: number;
  title: string;
  onSubmit: (reservationId: number, payload: ShipPayload) => Promise<void>;
  onClose: () => void;
}

export function ShipSheet({ reservationId, title, onSubmit, onClose }: ShipSheetProps) {
  const [isClosing, setIsClosing] = useState(false);
  const [ttn, setTtn] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    setSubmitting(true);
    try {
      const trimmedTtn = ttn.trim();
      await onSubmit(reservationId, { ttn: trimmedTtn || undefined });
      handleClose();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося відправити резерв"));
      setSubmitting(false);
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
        aria-label={`Відправити: ${title}`}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label release-sheet-title">Відправити: {title}</span>
          <button type="button" className="sheet-close" aria-label="Закрити" onClick={handleClose}>
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {error ? <p className="error-banner">{error}</p> : null}

          <label className="form-field">
            <span>ТТН (можна додати пізніше)</span>
            <input
              type="text"
              value={ttn}
              onChange={(event) => setTtn(event.target.value)}
              placeholder="20450123456789"
            />
          </label>

          <div className="modal-actions">
            <button type="button" onClick={handleClose} disabled={submitting}>
              Скасувати
            </button>
            <button type="submit" disabled={submitting}>
              {submitting ? "Відправляємо..." : "Відправлено"}
            </button>
          </div>
        </form>
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
