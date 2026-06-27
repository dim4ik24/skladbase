import { Pencil } from "lucide-react";
import type { Product, ReserveInput } from "../types";
import { VariantRow } from "./VariantRow";

interface ProductCardProps {
  product: Product;
  writable: boolean;
  isFrozen?: boolean;
  onFrozenAction?: () => void;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onEdit: (product: Product) => void;
}

export function ProductCard({
  product,
  writable,
  isFrozen = false,
  onFrozenAction,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onEdit,
}: ProductCardProps) {
  const sortedPhotos = [...product.photos].sort((a, b) => a.position - b.position);
  const coverUrl =
    sortedPhotos[0]?.url ??
    product.variants.find((v) => v.photo_url)?.photo_url ??
    null;
  const stripPhotos = sortedPhotos.slice(1);

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

      {stripPhotos.length > 0 ? (
        <div className="photo-strip" aria-label="Додаткові фото товару">
          {stripPhotos.map((ph) => (
            <img key={ph.id} src={ph.url} alt="" className="photo-strip-thumb" />
          ))}
        </div>
      ) : null}

      <ul className="variant-list">
        {product.variants.map((variant) => (
          <VariantRow
            key={variant.id}
            variant={variant}
            isFrozen={isFrozen}
            onFrozenAction={onFrozenAction}
            onRestock={onRestock}
            onAdjust={onAdjust}
            onUploadPhoto={onUploadPhoto}
            onReserve={onReserve}
          />
        ))}
      </ul>
    </article>
  );
}
