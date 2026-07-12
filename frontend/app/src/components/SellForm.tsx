import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { errorMessage } from "../errors";

interface SellFormProps {
  variantId: number;
  maxQty: number;
  onSubmit: (variantId: number, qty: number, withShipping: boolean) => Promise<void>;
  onCancel: () => void;
}

export function SellForm({ variantId, maxQty, onSubmit, onCancel }: SellFormProps) {
  const { t } = useTranslation();
  const [qty, setQty] = useState("1");
  const [withShipping, setWithShipping] = useState(false);
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

    setSubmitting(true);
    try {
      await onSubmit(variantId, qtyNumber, withShipping);
    } catch (err) {
      setError(errorMessage(err, t("sell.failed")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="sell-form" onSubmit={handleSubmit}>
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

      <label className="flex items-center gap-2 text-sm text-text mb-2">
        <input
          type="checkbox"
          checked={withShipping}
          onChange={(event) => setWithShipping(event.target.checked)}
        />
        {t("sell.withShippingLabel")}
      </label>

      <div className="modal-actions">
        <button type="button" onClick={onCancel} disabled={submitting}>
          {t("common.cancel")}
        </button>
        <button type="submit" disabled={submitting}>
          {submitting ? t("sell.submitting") : t("sell.submit")}
        </button>
      </div>
    </form>
  );
}
