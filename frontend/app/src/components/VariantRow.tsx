import { Pencil } from "lucide-react";
import { useState } from "react";
import type { ChangeEvent } from "react";
import { errorMessage } from "../errors";
import type { ReserveInput, TemplateField, Variant, VariantPatchPayload } from "../types";
import { ReserveForm } from "./ReserveForm";
import { VariantEditForm } from "./VariantEditForm";

interface VariantRowProps {
  variant: Variant;
  axes: TemplateField[];
  autoOpenEdit?: boolean;
  isFrozen?: boolean;
  onFrozenAction?: () => void;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onPatchVariant: (variantId: number, patch: VariantPatchPayload) => Promise<void>;
  onDeleteVariant: (variantId: number) => Promise<void>;
}

export function VariantRow({
  variant,
  axes,
  autoOpenEdit = false,
  isFrozen = false,
  onFrozenAction,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onPatchVariant,
  onDeleteVariant,
}: VariantRowProps) {
  const axisLabel = Object.values(variant.axis_values).join(" / ");
  const [showReserveForm, setShowReserveForm] = useState(false);
  const [showEditForm, setShowEditForm] = useState(autoOpenEdit);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setPhotoError(null);
    setUploading(true);
    try {
      await onUploadPhoto(variant.id, file);
    } catch (err) {
      setPhotoError(errorMessage(err, "Не вдалося завантажити фото"));
    } finally {
      setUploading(false);
    }
  }

  async function handleReserveSubmit(variantId: number, payload: ReserveInput) {
    await onReserve(variantId, payload);
    setShowReserveForm(false);
  }

  return (
    <li className="variant-row">
      <div className="variant-photo">
        {variant.photo_url ? (
          <img src={variant.photo_url} alt="" />
        ) : (
          <div className="variant-photo-placeholder" aria-hidden="true">
            📦
          </div>
        )}
        <label
          className="variant-photo-upload"
          onClick={
            isFrozen
              ? (e) => {
                  e.preventDefault();
                  onFrozenAction?.();
                }
              : undefined
          }
        >
          {uploading ? "..." : "📷"}
          <input
            type="file"
            accept="image/*"
            hidden
            disabled={uploading}
            onChange={handleFileChange}
            aria-label={`Завантажити фото: ${variant.sku ?? variant.id}`}
          />
        </label>
      </div>

      <div className="variant-main">
        <div className="variant-info">
          {axisLabel ? <span className="variant-axis">{axisLabel}</span> : null}
          <span className="variant-price">{variant.price} ₴</span>
          {variant.sku ? <span className="variant-sku">{variant.sku}</span> : null}
          {photoError ? <span className="error-banner">{photoError}</span> : null}
          <div className="variant-stock-trio">
            <span>складі: {variant.on_hand}</span>
            <span>резерв: {variant.reserved}</span>
            <div className="variant-available">
              <span data-testid={`available-${variant.id}`}>{variant.available} шт.</span>
              {variant.available === 0 ? (
                <span className="badge badge-out">нема</span>
              ) : variant.available <= variant.low_stock_threshold ? (
                <span className="badge badge-low">мало</span>
              ) : null}
            </div>
          </div>
        </div>
        <div className="variant-controls">
          <button
            type="button"
            aria-label={`Зменшити залишок: ${variant.sku ?? variant.id}`}
            aria-disabled={isFrozen}
            disabled={variant.on_hand <= 0}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              onAdjust(variant.id, variant.on_hand - 1);
            }}
          >
            −
          </button>
          <button
            type="button"
            aria-label={`Збільшити залишок: ${variant.sku ?? variant.id}`}
            aria-disabled={isFrozen}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              onRestock(variant.id, 1);
            }}
          >
            +
          </button>
          <button
            type="button"
            aria-disabled={isFrozen}
            disabled={variant.available <= 0}
            onClick={() => {
              if (isFrozen) { onFrozenAction?.(); return; }
              setShowReserveForm((prev) => !prev);
            }}
          >
            Відклади
          </button>
          <button
            type="button"
            aria-label={`Редагувати варіант: ${variant.sku ?? variant.id}`}
            onClick={() => {
              setShowReserveForm(false);
              setShowEditForm((prev) => !prev);
            }}
          >
            <Pencil size={13} />
          </button>
        </div>
      </div>

      {showReserveForm ? (
        <ReserveForm
          variantId={variant.id}
          maxQty={variant.available}
          onSubmit={handleReserveSubmit}
          onCancel={() => setShowReserveForm(false)}
        />
      ) : null}

      {showEditForm ? (
        <VariantEditForm
          variant={variant}
          axes={axes}
          onSave={(patch) => onPatchVariant(variant.id, patch)}
          onDelete={() => onDeleteVariant(variant.id)}
          onCancel={() => setShowEditForm(false)}
        />
      ) : null}
    </li>
  );
}
