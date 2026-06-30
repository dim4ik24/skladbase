import gsap from "gsap";
import { Flip } from "gsap/Flip";
import { useLayoutEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { ProductCard } from "../components/ProductCard";
import { ProductModal } from "../components/ProductModal";
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

gsap.registerPlugin(Flip);

type SortField = "name" | "price" | "stock" | "date";

const SORT_LABELS: Record<SortField, string> = {
  name: "Назва",
  price: "Ціна",
  stock: "Залишок",
  date: "Дата",
};

interface SkladScreenProps {
  products: Product[];
  templates: Template[];
  reservations: Reservation[];
  loading: boolean;
  writable: boolean;
  atLimit: boolean;
  maxProducts: number | null;
  activeCount: number;
  variantLabel: (variantId: number) => string;
  onRestock: (variantId: number, qty: number) => Promise<void>;
  onAdjust: (variantId: number, newOnHand: number) => Promise<void>;
  onUploadPhoto: (variantId: number, file: File) => Promise<void>;
  onReserve: (variantId: number, payload: ReserveInput) => Promise<void>;
  onRelease: (id: number) => Promise<void>;
  onFulfill: (id: number) => Promise<void>;
  onCreateProduct: (payload: ProductInput) => Promise<Product>;
  onUpdateProduct: (productId: number, patch: ProductPatch) => Promise<void>;
  onFrozenAction: () => void;
  onAddAtLimit: () => void;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  isOwner?: boolean;
  onTemplateAdded?: (template: Template) => void;
  photosAllowed: boolean;
  onUploadProductPhoto: (productId: number, file: File) => Promise<void>;
  onDeleteProductPhoto: (productId: number, photoId: number) => Promise<void>;
}

export function SkladScreen({
  products,
  templates,
  reservations,
  loading,
  writable,
  atLimit,
  maxProducts,
  activeCount,
  variantLabel,
  onRestock,
  onAdjust,
  onUploadPhoto,
  onReserve,
  onRelease,
  onFulfill,
  onCreateProduct,
  onUpdateProduct,
  onFrozenAction,
  onAddAtLimit,
  scrollContainerRef,
  isOwner,
  onTemplateAdded,
  photosAllowed,
  onUploadProductPhoto,
  onDeleteProductPhoto,
}: SkladScreenProps) {
  const [query, setQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [showReservations, setShowReservations] = useState(false);

  // null = modal closed; "create" = create mode; Product = edit mode
  const [modalProduct, setModalProduct] = useState<Product | "create" | null>(null);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const flipStateRef = useRef<ReturnType<typeof Flip.getState> | null>(null);

  function captureFlip() {
    if (!wrapperRef.current) return;
    const items = wrapperRef.current.querySelectorAll<Element>("[data-flip]");
    if (items.length > 0) {
      flipStateRef.current = Flip.getState(items);
    }
  }

  const filteredProducts = products.filter((p) => {
    const q = query.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      p.variants.some((v) => v.sku?.toLowerCase().includes(q))
    );
  });

  const sortedProducts = [...filteredProducts].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    switch (sortField) {
      case "name":
        return a.name.localeCompare(b.name, "uk") * dir;
      case "price": {
        const aMin = a.variants.length > 0
          ? Math.min(...a.variants.map((v) => parseFloat(v.price)))
          : 0;
        const bMin = b.variants.length > 0
          ? Math.min(...b.variants.map((v) => parseFloat(v.price)))
          : 0;
        return (aMin - bMin) * dir;
      }
      case "stock": {
        const aSum = a.variants.reduce((s, v) => s + v.available, 0);
        const bSum = b.variants.reduce((s, v) => s + v.available, 0);
        return (aSum - bSum) * dir;
      }
      case "date": {
        const aDate = a.created_at ?? "";
        const bDate = b.created_at ?? "";
        return aDate.localeCompare(bDate) * dir;
      }
    }
  });

  function handleSearchChange(e: React.ChangeEvent<HTMLInputElement>) {
    captureFlip();
    setQuery(e.target.value);
  }

  function handleSortClick(field: SortField) {
    captureFlip();
    if (field === sortField) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "date" ? "desc" : "asc");
    }
  }

  useLayoutEffect(() => {
    if (!flipStateRef.current || !wrapperRef.current) return;
    const state = flipStateRef.current;
    flipStateRef.current = null;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const items = wrapperRef.current.querySelectorAll<Element>("[data-flip]");

    Flip.from(state, {
      targets: items,
      duration: 0.4,
      ease: "power1.inOut",
      stagger: 0.03,
      absolute: true,
      onEnter: (els: Element[]) => {
        gsap.fromTo(els, { opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1, duration: 0.3 });
      },
      onLeave: (els: Element[]) => {
        gsap.to(els, { opacity: 0, scale: 0.85, duration: 0.2 });
      },
    });
  }, [query, sortField, sortDir]);

  return (
    <>
      {maxProducts !== null ? (
        <p className="slot-counter">{activeCount}/{maxProducts} активних</p>
      ) : null}

      <div className="toolbar">
        <input
          className="search-input"
          type="search"
          placeholder="Пошук товарів..."
          value={query}
          onChange={handleSearchChange}
          aria-label="Пошук товарів"
        />
        <button
          type="button"
          aria-disabled={atLimit}
          onClick={() => {
            if (atLimit) { onAddAtLimit(); return; }
            setModalProduct("create");
          }}
        >
          Додати товар
        </button>
        <button type="button" onClick={() => setShowReservations((prev) => !prev)}>
          Резерви ({reservations.length})
        </button>
      </div>

      <div className="sort-bar" role="group" aria-label="Сортування">
        {(Object.keys(SORT_LABELS) as SortField[]).map((field) => (
          <button
            key={field}
            type="button"
            className={`sort-btn${sortField === field ? " sort-btn--active" : ""}`}
            onClick={() => handleSortClick(field)}
            aria-pressed={sortField === field}
          >
            {SORT_LABELS[field]}
            {sortField === field ? (sortDir === "asc" ? " ↑" : " ↓") : null}
          </button>
        ))}
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
      ) : sortedProducts.length === 0 ? (
        <p className="status-text">Нічого не знайдено</p>
      ) : (
        <div className="product-grid" ref={wrapperRef}>
          {sortedProducts.map((product) => (
            <div key={product.id} data-flip={product.id}>
              <ProductCard
                product={product}
                writable={writable}
                isFrozen={product.is_frozen}
                onEdit={(p) => setModalProduct(p)}
              />
            </div>
          ))}
        </div>
      )}

      {modalProduct !== null ? (
        <ProductModal
          product={modalProduct === "create" ? null : modalProduct}
          products={products}
          templates={templates}
          photosAllowed={photosAllowed}
          isOwner={isOwner}
          onTemplateAdded={onTemplateAdded}
          onCreateProduct={onCreateProduct}
          onUpdateProduct={onUpdateProduct}
          onUploadProductPhoto={onUploadProductPhoto}
          onDeleteProductPhoto={onDeleteProductPhoto}
          onRestock={onRestock}
          onAdjust={onAdjust}
          onUploadPhoto={onUploadPhoto}
          onReserve={onReserve}
          onFrozenAction={onFrozenAction}
          onClose={() => setModalProduct(null)}
        />
      ) : null}
    </>
  );
}
