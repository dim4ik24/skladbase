import { useState } from "react";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";
import type { AdjustPayload, WriteOffReason } from "../types";

interface WriteOffFormProps {
  variantId: number;
  maxQty: number;
  onSubmit: (variantId: number, payload: AdjustPayload) => Promise<void>;
  onCancel: () => void;
}

const REASONS: { value: WriteOffReason; label: string }[] = [
  { value: "sold", label: "💰 Продано" },
  { value: "defect", label: "🔧 Брак" },
  { value: "correction", label: "✏️ Корекція" },
  { value: "other", label: "❓ Інше" },
];

export function WriteOffForm({ variantId, maxQty, onSubmit, onCancel }: WriteOffFormProps) {
  const [qty, setQty] = useState("1");
  const [reason, setReason] = useState<WriteOffReason | null>(null);
  const [comment, setComment] = useState("");
  const [commentMissing, setCommentMissing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const qtyNumber = Number(qty);
    if (!Number.isInteger(qtyNumber) || qtyNumber <= 0 || qtyNumber > maxQty) {
      setError(`Кількість має бути від 1 до ${maxQty}`);
      return;
    }
    if (!reason) {
      setError("Оберіть причину списання");
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
      await onSubmit(variantId, {
        qty: qtyNumber,
        reason,
        comment: trimmedComment || undefined,
      });
    } catch (err) {
      setError(errorMessage(err, "Не вдалося списати товар"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="write-off-form" onSubmit={handleSubmit}>
      {error ? <p className="error-banner">{error}</p> : null}

      <label className="form-field">
        <span>Кількість (доступно {maxQty})</span>
        <input
          type="number"
          min="1"
          max={maxQty}
          value={qty}
          onChange={(event) => setQty(event.target.value)}
          required
        />
      </label>

      <div className="write-off-reasons" role="group" aria-label="Причина списання">
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
          {submitting ? "Списуємо..." : "Списати"}
        </button>
      </div>
    </form>
  );
}
