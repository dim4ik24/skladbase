import { chipLetter, resolveChipColor } from "../lib/variantColor";
import type { TemplateField, Variant } from "../types";

interface VariantTagProps {
  variant: Variant;
  axes: TemplateField[];
  photoUrl: string | null;
  onClick: () => void;
}

function fmt(p: string): string {
  const n = parseFloat(p);
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function VariantTag({ variant, axes, photoUrl, onClick }: VariantTagProps) {
  const axisLabel = Object.values(variant.axis_values).filter(Boolean).join(" / ");
  const chipColor = resolveChipColor(axes, variant.axis_values);
  const letter = chipLetter(axes, variant.axis_values);
  const isWhite = chipColor === "#FFFFFF";

  const stockBg =
    variant.available === 0 || variant.available <= variant.low_stock_threshold
      ? "var(--state-low)"
      : "var(--state-ok)";

  return (
    <button
      type="button"
      className="variant-tag"
      onClick={onClick}
      aria-label={`Варіант: ${axisLabel || variant.sku || String(variant.id)}`}
    >
      {chipColor !== null ? (
        <span
          className="variant-chip"
          style={{
            background: chipColor,
            border: isWhite ? "1.5px solid var(--line)" : undefined,
          }}
        />
      ) : photoUrl ? (
        <img src={photoUrl} alt="" className="variant-chip variant-chip--photo" />
      ) : (
        <span className="variant-chip variant-chip--neutral">{letter}</span>
      )}

      <span className="variant-tag-center">
        <span className="variant-tag-axis">
          {axisLabel || variant.sku || `#${variant.id}`}
        </span>
        <span className="variant-tag-price">{fmt(variant.price)} ₴</span>
      </span>

      <span className="variant-tag-right">
        <span className="stock-bar" style={{ background: stockBg }} />
        {variant.reserved > 0 ? <span className="stock-bar stock-bar--rsv" /> : null}
        <span
          className="stock-count"
          data-testid={`available-${variant.id}`}
        >
          {variant.available} шт.
        </span>
        {variant.available === 0 ? (
          <span className="badge badge-out">нема</span>
        ) : variant.available <= variant.low_stock_threshold ? (
          <span className="badge badge-low">мало</span>
        ) : null}
      </span>
    </button>
  );
}
