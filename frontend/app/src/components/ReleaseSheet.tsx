import { useState } from "react";
import { createPortal } from "react-dom";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";
import type { ReleasePayload, ReleaseReason } from "../types";

interface ReleaseSheetProps {
  reservationId: number;
  title: string;
  onSubmit: (reservationId: number, payload: ReleasePayload) => Promise<void>;
  onClose: () => void;
}

const REASONS: { value: ReleaseReason; label: string }[] = [
  { value: "customer_changed_mind", label: "Клієнт передумав" },
  { value: "unresponsive", label: "Клієнт не виходить на зв'язок" },
  { value: "mistaken_reservation", label: "Резерв створено помилково" },
  { value: "other", label: "❓ Інша причина" },
];

export function ReleaseSheet({ reservationId, title, onSubmit, onClose }: ReleaseSheetProps) {
  const [isClosing, setIsClosing] = useState(false);
  const [reason, setReason] = useState<ReleaseReason | null>(null);
  const [comment, setComment] = useState("");
  const [commentMissing, setCommentMissing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleClose() {
    setIsClosing(true);
    setTimeout(onClose, 250);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!reason) {
      setError("Оберіть причину зняття");
      return;
    }
    const trimmedComment = comment.trim();
    if (reason === "other" && !trimmedComment) {
      setCommentMissing(true);
      return;
    }
    setCommentMissing(false);

    setSubmitting(true);
    try {
      await onSubmit(reservationId, {
        reason,
        comment: trimmedComment || undefined,
      });
      handleClose();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося зняти резерв"));
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
        aria-label={`Зняти резерв: ${title}`}
        className={`variant-sheet${isClosing ? " variant-sheet--closing" : ""}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-header">
          <span className="sheet-axis-label release-sheet-title">
            Чому знімаєте резерв «{title}»?
          </span>
          <button type="button" className="sheet-close" aria-label="Закрити" onClick={handleClose}>
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {error ? <p className="error-banner">{error}</p> : null}

          <div className="write-off-reasons" role="group" aria-label="Чому знімаєте резерв?">
            {REASONS.map((r) => (
              <button
                key={r.value}
                type="button"
                className={`write-off-reason-chip${
                  reason === r.value ? " write-off-reason-chip--active" : ""
                }`}
                aria-pressed={reason === r.value}
                onClick={() => setReason(r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>

          {reason === "other" ? (
            <label className="form-field">
              <span>Коментар (обов'язково)</span>
              <input
                type="text"
                value={comment}
                onChange={(event) => {
                  setComment(event.target.value);
                  setCommentMissing(false);
                }}
                aria-invalid={commentMissing}
                className={commentMissing ? "field-invalid" : undefined}
              />
            </label>
          ) : null}

          <div className="modal-actions">
            <button type="button" onClick={handleClose} disabled={submitting}>
              Скасувати
            </button>
            <button type="submit" disabled={submitting}>
              {submitting ? "Знімаємо..." : "Підтвердити"}
            </button>
          </div>
        </form>
      </div>
    </>
  );

  return createPortal(sheet, document.body);
}
