import { useState } from "react";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";
import type { ReleasePayload, ReleaseReason } from "../types";

interface ReleaseFormProps {
  reservationId: number;
  onSubmit: (reservationId: number, payload: ReleasePayload) => Promise<void>;
  onCancel: () => void;
}

const REASONS: { value: ReleaseReason; label: string }[] = [
  { value: "customer_changed_mind", label: "Клієнт передумав" },
  { value: "unresponsive", label: "Не відповідає" },
  { value: "mistaken_reservation", label: "Помилковий резерв" },
  { value: "other", label: "❓ Інше" },
];

export function ReleaseForm({ reservationId, onSubmit, onCancel }: ReleaseFormProps) {
  const [reason, setReason] = useState<ReleaseReason | null>(null);
  const [comment, setComment] = useState("");
  const [commentMissing, setCommentMissing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    } catch (err) {
      setError(errorMessage(err, "Не вдалося зняти резерв"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="write-off-form" onSubmit={handleSubmit}>
      {error ? <p className="error-banner">{error}</p> : null}

      <div className="write-off-reasons" role="group" aria-label="Причина зняття">
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
        <button type="button" onClick={onCancel} disabled={submitting}>
          Скасувати
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? "Знімаємо..." : "Підтвердити"}
        </button>
      </div>
    </form>
  );
}
