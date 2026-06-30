import { useState } from "react";
import { errorMessage } from "../errors";
import type { TemplateField, Variant, VariantPatchPayload } from "../types";

interface VariantEditFormProps {
  variant: Variant;
  axes: TemplateField[];
  onSave: (patch: VariantPatchPayload) => Promise<void>;
  onDelete: () => Promise<void>;
  onCancel: () => void;
}

export function VariantEditForm({ variant, axes, onSave, onDelete, onCancel }: VariantEditFormProps) {
  const [price, setPrice] = useState(variant.price);
  const [sku, setSku] = useState(variant.sku ?? "");
  const [axisValues, setAxisValues] = useState<Record<string, string>>({ ...variant.axis_values });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const axisLabel = Object.values(variant.axis_values).filter(Boolean).join(" / ") || `#${variant.id}`;

  async function handleSave() {
    setError(null);
    setSaving(true);
    const patch: VariantPatchPayload = { price };
    patch.sku = sku.trim() || null;
    if (axes.length > 0) patch.axis_values = axisValues;
    try {
      await onSave(patch);
      onCancel();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося зберегти варіант"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setError(null);
    setDeleting(true);
    try {
      await onDelete();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося видалити варіант"));
      setConfirmDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="variant-edit-form">
      {error ? <p className="error-banner">{error}</p> : null}

      <label className="form-field">
        <span>Ціна</span>
        <input
          aria-label="Ціна"
          type="number"
          min="0"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
        />
      </label>

      <label className="form-field">
        <span>Артикул</span>
        <input
          aria-label="Артикул"
          type="text"
          value={sku}
          onChange={(e) => setSku(e.target.value)}
          placeholder="необов'язково"
        />
      </label>

      {axes.map((axis) => (
        <label className="form-field" key={axis.key}>
          <span>{axis.label}</span>
          {axis.type === "enum" ? (
            <select
              aria-label={axis.label}
              value={axisValues[axis.key] ?? ""}
              onChange={(e) =>
                setAxisValues((prev) => ({ ...prev, [axis.key]: e.target.value }))
              }
            >
              {(axis.options ?? []).map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : (
            <input
              aria-label={axis.label}
              type="text"
              value={axisValues[axis.key] ?? ""}
              onChange={(e) =>
                setAxisValues((prev) => ({ ...prev, [axis.key]: e.target.value }))
              }
            />
          )}
        </label>
      ))}

      <div className="variant-edit-actions">
        <button type="button" onClick={onCancel} disabled={saving || deleting}>
          Скасувати
        </button>
        <button type="button" onClick={() => void handleSave()} disabled={saving || deleting}>
          {saving ? "Зберігаємо..." : "Зберегти"}
        </button>
      </div>

      <div className="variant-delete-zone">
        {confirmDelete ? (
          <>
            <p className="variant-delete-confirm">
              Видалити варіант <strong>{axisLabel}</strong>?
            </p>
            <div className="variant-edit-actions">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
              >
                Ні
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={() => void handleDelete()}
                disabled={deleting}
              >
                {deleting ? "Видаляємо..." : "Так, видалити"}
              </button>
            </div>
          </>
        ) : (
          <button
            type="button"
            className="btn-danger-outline"
            onClick={() => setConfirmDelete(true)}
            disabled={saving}
          >
            Видалити
          </button>
        )}
      </div>
    </div>
  );
}
