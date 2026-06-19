import { useState } from "react";
import { AlignLeft, Pencil, Tag } from "lucide-react";
import type { Product, ProductPatch, ReserveInput } from "../types";
import { InlineEditCard } from "./ui/InlineEditCard";
import { VariantRow } from "./VariantRow";

interface ProductCardProps {
  product: Product;
  writable: boolean;
  onRestock: (variantId: number, qty: number) => void;
  onAdjust: (variantId: number, newOnHand: number) => void;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onUpdateProduct: (productId: number, patch: ProductPatch) => Promise<void>;
}

export function ProductCard({
  product,
  writable,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onUpdateProduct,
}: ProductCardProps) {
  const [editing, setEditing] = useState(false);
  const photoUrl = product.variants.find((variant) => variant.photo_url)?.photo_url ?? null;

  function handleSaveField(key: string, value: string) {
    if (key === "name") void onUpdateProduct(product.id, { name: value });
    else if (key === "description") void onUpdateProduct(product.id, { description: value });
  }

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

      <div className="flex items-center justify-between gap-2">
        <h3 className="product-name">{product.name}</h3>
        <button
          type="button"
          disabled={!writable}
          aria-label={`Редагувати товар: ${product.name}`}
          onClick={() => setEditing((prev) => !prev)}
          className="shrink-0 rounded-lg p-1 text-cream/50 transition-colors hover:bg-white/[0.06] hover:text-cream disabled:cursor-not-allowed disabled:opacity-30"
        >
          <Pencil size={15} />
        </button>
      </div>

      {editing ? (
        <InlineEditCard
          title="Товар"
          fields={[
            { key: "name", icon: Tag, label: "Назва", value: product.name },
            {
              key: "description",
              icon: AlignLeft,
              label: "Опис",
              value: product.description ?? "",
              multiline: true,
            },
          ]}
          onSave={handleSaveField}
        />
      ) : null}

      <ul className="variant-list">
        {product.variants.map((variant) => (
          <VariantRow
            key={variant.id}
            variant={variant}
            writable={writable}
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
