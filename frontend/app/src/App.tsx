import { useEffect, useState } from "react";
import * as api from "./api";
import { Header } from "./components/Header";
import { ProductCard } from "./components/ProductCard";
import { ProductFormModal } from "./components/ProductFormModal";
import { ReservationsPanel } from "./components/ReservationsPanel";
import { errorMessage } from "./errors";
import { initTelegram, setAccentColor } from "./telegram";
import type { Product, ProductInput, Reservation, ReserveInput, Shop, Template, Variant } from "./types";

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showProductForm, setShowProductForm] = useState(false);
  const [showReservations, setShowReservations] = useState(false);

  useEffect(() => {
    initTelegram();
    let mounted = true;

    async function load() {
      try {
        const [meResult, productsResult, templatesResult, reservationsResult] =
          await Promise.all([
            api.getMe(),
            api.getProducts(),
            api.getTemplates(),
            api.getReservations(),
          ]);
        if (!mounted) return;
        setShop(meResult);
        setAccentColor(meResult.accent_color);
        setProducts(productsResult);
        setTemplates(templatesResult);
        setReservations(reservationsResult);
      } catch (err) {
        if (!mounted) return;
        setError(errorMessage(err, "Не вдалося завантажити дані"));
      } finally {
        if (mounted) setLoading(false);
      }
    }

    void load();
    return () => {
      mounted = false;
    };
  }, []);

  function applyVariantUpdate(updated: Variant) {
    setProducts((prev) =>
      prev.map((product) => ({
        ...product,
        variants: product.variants.map((variant) =>
          variant.id === updated.id ? updated : variant,
        ),
      })),
    );
  }

  function patchVariant(variantId: number, patch: Partial<Variant>) {
    setProducts((prev) =>
      prev.map((product) => ({
        ...product,
        variants: product.variants.map((variant) =>
          variant.id === variantId ? { ...variant, ...patch } : variant,
        ),
      })),
    );
  }

  async function handleRestock(variantId: number, qty: number) {
    try {
      applyVariantUpdate(await api.restock(variantId, qty));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося поповнити залишок"));
    }
  }

  async function handleAdjust(variantId: number, newOnHand: number) {
    try {
      applyVariantUpdate(await api.adjust(variantId, newOnHand));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося оновити залишок"));
    }
  }

  async function handleCreateProduct(payload: ProductInput) {
    const product = await api.createProduct(payload);
    setProducts((prev) => [...prev, product]);
    setShowProductForm(false);
  }

  async function handleUploadPhoto(variantId: number, file: File) {
    // Помилку показує сам VariantRow поруч із контролом — без дубля у глобальному банері.
    applyVariantUpdate(await api.uploadVariantPhoto(variantId, file));
  }

  async function handleReserve(variantId: number, payload: ReserveInput) {
    // Помилку показує ReserveForm поруч із полями — без дубля у глобальному банері.
    const reservation = await api.reserve(variantId, payload);
    const variant = products
      .flatMap((product) => product.variants)
      .find((v) => v.id === variantId);
    const reserved = (variant?.reserved ?? 0) + reservation.qty;
    const onHand = variant?.on_hand ?? 0;
    patchVariant(variantId, { reserved, available: onHand - reserved });
    setReservations((prev) => [reservation, ...prev]);
  }

  function applyReservationClosed(reservation: Reservation, kind: "release" | "fulfill") {
    const variant = products
      .flatMap((product) => product.variants)
      .find((v) => v.id === reservation.variant_id);
    if (variant) {
      const reserved = variant.reserved - reservation.qty;
      const onHand = kind === "fulfill" ? variant.on_hand - reservation.qty : variant.on_hand;
      patchVariant(variant.id, { reserved, on_hand: onHand, available: onHand - reserved });
    }
    setReservations((prev) => prev.filter((r) => r.id !== reservation.id));
  }

  async function handleRelease(reservationId: number) {
    try {
      const reservation = await api.releaseReservation(reservationId);
      applyReservationClosed(reservation, "release");
    } catch (err) {
      setError(errorMessage(err, "Не вдалося знять резерв"));
    }
  }

  async function handleFulfill(reservationId: number) {
    try {
      const reservation = await api.fulfillReservation(reservationId);
      applyReservationClosed(reservation, "fulfill");
    } catch (err) {
      setError(errorMessage(err, "Не вдалося оформити продаж"));
    }
  }

  function variantLabel(variantId: number): string {
    for (const product of products) {
      const variant = product.variants.find((v) => v.id === variantId);
      if (variant) {
        const axis = Object.values(variant.axis_values).join(" / ");
        return axis ? `${product.name} (${axis})` : product.name;
      }
    }
    return `Варіант #${variantId}`;
  }

  const filteredProducts = products.filter((product) =>
    product.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="app">
      <Header shop={shop} />

      {error ? <p className="error-banner">{error}</p> : null}

      <div className="toolbar">
        <input
          className="search-input"
          type="search"
          placeholder="Пошук товарів..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Пошук товарів"
        />
        <button type="button" onClick={() => setShowProductForm(true)}>
          Додати товар
        </button>
        <button type="button" onClick={() => setShowReservations((prev) => !prev)}>
          Резерви ({reservations.length})
        </button>
      </div>

      {showReservations ? (
        <section className="reservations-section">
          <h2>Резерви</h2>
          <ReservationsPanel
            reservations={reservations}
            variantLabel={variantLabel}
            onRelease={handleRelease}
            onFulfill={handleFulfill}
          />
        </section>
      ) : null}

      {loading ? (
        <p className="status-text">Завантаження...</p>
      ) : filteredProducts.length === 0 ? (
        <p className="status-text">Нічого не знайдено</p>
      ) : (
        <div className="product-grid">
          {filteredProducts.map((product) => (
            <ProductCard
              key={product.id}
              product={product}
              onRestock={handleRestock}
              onAdjust={handleAdjust}
              onUploadPhoto={handleUploadPhoto}
              onReserve={handleReserve}
            />
          ))}
        </div>
      )}

      {showProductForm ? (
        <ProductFormModal
          templates={templates}
          onSubmit={handleCreateProduct}
          onClose={() => setShowProductForm(false)}
        />
      ) : null}
    </div>
  );
}
