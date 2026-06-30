import { Pencil } from "lucide-react";
import type { Product } from "../types";

interface ProductCardProps {
  product: Product;
  writable: boolean;
  isFrozen?: boolean;
  onFrozenAction?: () => void;
  onEdit: (product: Product) => void;
}

function variantBadge(n: number): string {
  if (n % 10 === 1 && n % 100 !== 11) return `${n} варіант`;
  if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return `${n} варіанти`;
  return `${n} варіантів`;
}

export function ProductCard({
  product,
  writable,
  isFrozen = false,
  onFrozenAction,
  onEdit,
}: ProductCardProps) {
  const sortedPhotos = [...product.photos].sort((a, b) => a.position - b.position);
  const coverUrl =
    sortedPhotos[0]?.url ??
    product.variants.find((v) => v.photo_url)?.photo_url ??
    null;

  const prices = product.variants.map((v) => parseFloat(v.price));
  const minP = prices.length > 0 ? Math.min(...prices) : null;
  const maxP = prices.length > 0 ? Math.max(...prices) : null;
  const priceLabel =
    minP === null || maxP === null
      ? "—"
      : minP === maxP
        ? `${minP.toFixed(2)} ₴`
        : `${minP.toFixed(2)}–${maxP.toFixed(2)} ₴`;

  const totalAvailable = product.variants.reduce((s, v) => s + v.available, 0);

  return (
    <article className={`product-card${isFrozen ? " product-card--frozen" : ""}`}>
      <div className="product-photo">
        {coverUrl ? (
          <img src={coverUrl} alt={product.name} />
        ) : (
          <div className="product-photo-placeholder" aria-hidden="true">
            📦
          </div>
        )}
      </div>

      {isFrozen ? (
        <span className="frozen-badge">
          <span aria-hidden="true">🔒</span>
          {" "}Заморожено
        </span>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <h3 className="product-name">{product.name}</h3>
        <button
          type="button"
          disabled={!writable}
          aria-label={`Редагувати товар: ${product.name}`}
          onClick={() => {
            if (isFrozen) { onFrozenAction?.(); return; }
            onEdit(product);
          }}
          className="shrink-0 rounded-lg p-1 text-green-deep/40 transition-colors hover:bg-green/[0.08] hover:text-green-deep disabled:cursor-not-allowed disabled:opacity-30"
        >
          <Pencil size={15} />
        </button>
      </div>

      <div className="product-card-meta">
        <span className="product-price-range">{priceLabel}</span>
        <span className="product-stock-total">{totalAvailable} шт.</span>
        <span className="variant-count-badge">{variantBadge(product.variants.length)}</span>
      </div>
    </article>
  );
}
