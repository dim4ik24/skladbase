import { Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Product } from "../types";

interface ProductCardProps {
  product: Product;
  writable: boolean;
  isFrozen?: boolean;
  index?: number;
  onEdit: (product: Product) => void;
}

export function ProductCard({
  product,
  writable,
  isFrozen = false,
  index = 0,
  onEdit,
}: ProductCardProps) {
  const { t } = useTranslation();
  const sortedPhotos = [...product.photos].sort((a, b) => a.position - b.position);
  const coverUrl =
    sortedPhotos[0]?.url ??
    product.variants.find((v) => v.photo_url)?.photo_url ??
    null;

  const prices = product.variants.map((v) => parseFloat(v.price));
  const minP = prices.length > 0 ? Math.min(...prices) : null;
  const maxP = prices.length > 0 ? Math.max(...prices) : null;
  const fmt = (p: number) => (Number.isInteger(p) ? String(p) : p.toFixed(2));
  const priceLabel =
    minP === null || maxP === null
      ? "—"
      : minP === maxP
        ? `${fmt(minP)} ₴`
        : `${fmt(minP)}–${fmt(maxP)} ₴`;

  const totalAvailable = product.variants.reduce((s, v) => s + v.available, 0);

  return (
    <article
      className={`product-card${isFrozen ? " product-card--frozen" : ""}`}
      style={{ animationDelay: `${Math.min(index, 9) * 40}ms` }}
    >
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
          {" "}{t("product.frozenBadge")}
        </span>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <h3 className="product-name">{product.name}</h3>
        <button
          type="button"
          disabled={!writable}
          aria-label={t("product.editCardAriaLabel", { name: product.name })}
          onClick={() => onEdit(product)}
          className="shrink-0 rounded-lg p-1 text-green-deep/40 transition-colors hover:bg-green/[0.08] hover:text-green-deep disabled:cursor-not-allowed disabled:opacity-30"
        >
          <Pencil size={15} />
        </button>
      </div>

      <div className="product-card-meta">
        <span className="pcard-price">{priceLabel}</span>
        <div className="pcard-substats">
          <span className="pcard-stock">
            {totalAvailable} {t("common.unitsShort")}
          </span>
          <span className="pcard-variants">
            {t("product.variantsCount", { count: product.variants.length })}
          </span>
        </div>
      </div>
    </article>
  );
}
