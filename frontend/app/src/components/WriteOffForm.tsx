import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";
import type { AdjustPayload, WriteOffReason } from "../types";

interface WriteOffFormProps {
  variantId: number;
  maxQty: number;
  onSubmit: (variantId: number, payload: AdjustPayload) => Promise<void>;
  onCancel: () => void;
}

const REASONS: { value: WriteOffReason; labelKey: string }[] = [
  { value: "sold", labelKey: "reasons.sold" },
  { value: "defect", labelKey: "reasons.defect" },
  { value: "correction", labelKey: "reasons.correction" },
  { value: "other", labelKey: "reasons.otherShort" },
];

export function WriteOffForm({ variantId, maxQty, onSubmit, onCancel }: WriteOffFormProps) {
  const { t } = useTranslation();
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
      setError(t("common.qtyRange", { max: maxQty }));
      return;
    }
    if (!reason) {
      setError(t("writeOff.reasonMissing"));
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
      setError(errorMessage(err, t("writeOff.failed")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="write-off-form" onSubmit={handleSubmit}>
      {error ? <p className="error-banner">{error}</p> : null}

      <label className="form-field">
        <span>{t("common.qtyAvailable", { max: maxQty })}</span>
        <input
          type="number"
          min="1"
          max={maxQty}
          value={qty}
          onChange={(event) => setQty(event.target.value)}
          required
        />
      </label>

      <div
        className="write-off-reasons"
        role="group"
        aria-label={t("writeOff.reasonGroupAriaLabel")}
      >
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
            {t(r.labelKey)}
          </button>
        ))}
      </div>

      {reason === "other" ? (
        <label className="form-field">
          <span>{t("writeOff.commentLabel")}</span>
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
          {t("common.cancel")}
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? t("writeOff.submitting") : t("writeOff.submit")}
        </button>
      </div>
    </form>
  );
}
