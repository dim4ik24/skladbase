import type { Product, ReserveInput } from "../types";
import { VariantRow } from "./VariantRow";

interface ProductCardProps {
  product: Product;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
}

export function ProductCard({
  product,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
}: ProductCardProps) {
  const photoUrl = product.variants.find((variant) => variant.photo_url)?.photo_url ?? null;

  return (
    <article className="product-card">
      <div className="product-photo">
        {photoUrl ? (
          <img src={photoUrl} alt={product.name} />
        ) : (
          <div className="product-photo-placeholder" aria-hidden="true">
            📦
          </div>
        )}
      </div>
      <h3 className="product-name">{product.name}</h3>
      <ul className="variant-list">
        {product.variants.map((variant) => (
          <VariantRow
            key={variant.id}
            variant={variant}
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
