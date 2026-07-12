import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";
import type { ReserveInput } from "../types";

interface ReserveFormProps {
  variantId: number;
  maxQty: number;
  onSubmit: (variantId: number, payload: ReserveInput) => Promise<void>;
  onCancel: () => void;
}

export function ReserveForm({ variantId, maxQty, onSubmit, onCancel }: ReserveFormProps) {
  const { t } = useTranslation();
  const [qty, setQty] = useState("1");
  const [customerNote, setCustomerNote] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const qtyNumber = Number(qty);
    if (!Number.isInteger(qtyNumber) || qtyNumber <= 0) {
      setError(t("common.qtyPositive"));
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(variantId, {
        qty: qtyNumber,
        customer_note: customerNote.trim() || undefined,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
      });
    } catch (err) {
      setError(errorMessage(err, t("reservations.form.failed")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="reserve-form" onSubmit={handleSubmit}>
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

      <label className="form-field">
        <span>{t("reservations.form.customerNoteLabel")}</span>
        <input
          type="text"
          value={customerNote}
          onChange={(event) => setCustomerNote(event.target.value)}
          placeholder={t("reservations.form.customerNotePlaceholder")}
        />
      </label>

      <label className="form-field">
        <span>{t("reservations.form.expiresLabel")}</span>
        <input
          type="datetime-local"
          value={expiresAt}
          onChange={(event) => setExpiresAt(event.target.value)}
        />
      </label>

      <div className="modal-actions">
        <button type="button" onClick={onCancel} disabled={submitting}>
          {t("common.cancel")}
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? t("reservations.form.submitting") : t("reservations.form.submitButton")}
        </button>
      </div>
    </form>
  );
}
