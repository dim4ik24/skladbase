import { useState } from "react";
import type { ChangeEvent } from "react";
import { errorMessage } from "../errors";
import type { ReserveInput, Variant } from "../types";
import { ReserveForm } from "./ReserveForm";

interface VariantRowProps {
  variant: Variant;
  writable: boolean;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
}

export function VariantRow({
  variant,
  writable,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
}: VariantRowProps) {
  const axisLabel = Object.values(variant.axis_values).join(" / ");
  const [showReserveForm, setShowReserveForm] = useState(false);
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
        <label className="variant-photo-upload">
          {uploading ? "..." : "📷"}
          <input
            type="file"
            accept="image/*"
            hidden
            disabled={uploading || !writable}
            onChange={handleFileChange}
            aria-label={`Завантажити фото: ${variant.sku ?? variant.id}`}
          />
        </label>
      </div>

      <div className="variant-main">
        <div className="variant-info">
          {axisLabel ? <span className="variant-axis">{axisLabel}</span> : null}
          <span className="variant-price">{variant.price} ₴</span>
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
            disabled={variant.on_hand <= 0 || !writable}
            onClick={() => onAdjust(variant.id, variant.on_hand - 1)}
          >
            −
          </button>
          <button
            type="button"
            aria-label={`Збільшити залишок: ${variant.sku ?? variant.id}`}
            disabled={!writable}
            onClick={() => onRestock(variant.id, 1)}
          >
            +
          </button>
          <button
            type="button"
            disabled={variant.available <= 0 || !writable}
            onClick={() => setShowReserveForm((prev) => !prev)}
          >
            Відклади
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
    </li>
  );
}
