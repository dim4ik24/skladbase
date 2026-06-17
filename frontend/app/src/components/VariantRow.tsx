import type { Variant } from "../types";

interface VariantRowProps {
  variant: Variant;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
}

export function VariantRow({ variant, onRestock, onAdjust }: VariantRowProps) {
  const axisLabel = Object.values(variant.axis_values).join(" / ");

  return (
    <li className="variant-row">
      <div className="variant-info">
        {axisLabel ? <span className="variant-axis">{axisLabel}</span> : null}
        <span className="variant-price">{variant.price} ₴</span>
        <div className="variant-available">
          <span data-testid={`available-${variant.id}`}>{variant.available} шт.</span>
          {variant.available === 0 ? (
            <span className="badge badge-out">нема</span>
          ) : variant.available <= variant.low_stock_threshold ? (
            <span className="badge badge-low">мало</span>
          ) : null}
        </div>
      </div>
      <div className="variant-controls">
        <button
          type="button"
          aria-label={`Зменшити залишок: ${variant.sku ?? variant.id}`}
          disabled={variant.on_hand <= 0}
          onClick={() => onAdjust(variant.id, variant.on_hand - 1)}
        >
          −
        </button>
        <button
          type="button"
          aria-label={`Збільшити залишок: ${variant.sku ?? variant.id}`}
          onClick={() => onRestock(variant.id, 1)}
        >
          +
        </button>
      </div>
    </li>
  );
}
