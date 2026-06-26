import { motion } from "motion/react";
import { useState } from "react";
import type { RefObject } from "react";
import { ProductCard } from "../components/ProductCard";
import { ProductFormModal } from "../components/ProductFormModal";
import { ReservationsPanel } from "../components/ReservationsPanel";
import { ScrollFloat } from "../components/ScrollFloat";
import { Panel } from "../components/ui/Panel";
import type {
  Product,
  ProductInput,
  ProductPatch,
  Reservation,
  ReserveInput,
  Template,
} from "../types";

const CARD_VARIANTS = {
  hidden: { opacity: 0, y: 18 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.055, duration: 0.38, ease: [0, 0, 0.2, 1] as const },
  }),
} as const;

interface SkladScreenProps {
  products: Product[];
  templates: Template[];
  reservations: Reservation[];
  loading: boolean;
  writable: boolean;
  variantLabel: (variantId: number) => string;
  onRestock: (variantId: number, qty: number) => Promise<void>;
  onAdjust: (variantId: number, newOnHand: number) => Promise<void>;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onRelease: (id: number) => Promise<void>;
  onFulfill: (id: number) => Promise<void>;
  onCreateProduct: (payload: ProductInput) => Promise<void>;
  onUpdateProduct: (productId: number, patch: ProductPatch) => Promise<void>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

export function SkladScreen({
  products,
  templates,
  reservations,
  loading,
  writable,
  variantLabel,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onRelease,
  onFulfill,
  onCreateProduct,
  onUpdateProduct,
  scrollContainerRef,
}: SkladScreenProps) {
  const [query, setQuery] = useState("");
  const [showProductForm, setShowProductForm] = useState(false);
  const [showReservations, setShowReservations] = useState(false);

  const filteredProducts = products.filter((p) =>
    p.name.toLowerCase().includes(query.toLowerCase()),
  );

  async function handleSubmitCreate(payload: ProductInput) {
    await onCreateProduct(payload);
    setShowProductForm(false);
  }

  return (
    <>
      <div className="toolbar">
        <input
          className="search-input"
          type="search"
          placeholder="Пошук товарів..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Пошук товарів"
        />
        <button type="button" disabled={!writable} onClick={() => setShowProductForm(true)}>
          Додати товар
        </button>
        <button type="button" onClick={() => setShowReservations((prev) => !prev)}>
          Резерви ({reservations.length})
        </button>
      </div>

      {showReservations ? (
        <Panel as="section" className="reservations-section p-0">
          <ScrollFloat
            as="h2"
            className="section-title px-4 pt-4"
            scrollContainerRef={scrollContainerRef}
          >
            Резерви
          </ScrollFloat>
          <div className="px-4 pb-4">
            <ReservationsPanel
              reservations={reservations}
              writable={writable}
              variantLabel={variantLabel}
              onRelease={onRelease}
              onFulfill={onFulfill}
            />
          </div>
        </Panel>
      ) : null}

      <ScrollFloat as="h2" className="section-title" scrollContainerRef={scrollContainerRef}>
        Каталог
      </ScrollFloat>

      {loading ? (
        <p className="status-text">Завантаження…</p>
      ) : filteredProducts.length === 0 ? (
        <p className="status-text">Нічого не знайдено</p>
      ) : (
        <div className="product-grid">
          {filteredProducts.map((product, i) => (
            <motion.div
              key={product.id}
              custom={i}
              initial="hidden"
              animate="visible"
              variants={CARD_VARIANTS}
            >
              <ProductCard
                product={product}
                writable={writable}
                onRestock={onRestock}
                onAdjust={onAdjust}
                onUploadPhoto={onUploadPhoto}
                onReserve={onReserve}
                onUpdateProduct={onUpdateProduct}
              />
            </motion.div>
          ))}
        </div>
      )}

      {showProductForm ? (
        <ProductFormModal
          templates={templates}
          onSubmit={handleSubmitCreate}
          onClose={() => setShowProductForm(false)}
        />
      ) : null}
    </>
  );
}
