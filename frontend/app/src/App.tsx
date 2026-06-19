import { Ban, BookmarkCheck, Package, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import { AtmosphereBackground } from "./components/background/AtmosphereBackground";
import { DemoBanner } from "./components/DemoBanner";
import { Header } from "./components/Header";
import type { MetricCardData } from "./components/MetricCarousel";
import { MetricCarousel } from "./components/MetricCarousel";
import { ProductCard } from "./components/ProductCard";
import { ProductFormModal } from "./components/ProductFormModal";
import { ReservationsPanel } from "./components/ReservationsPanel";
import { ScrollFloat } from "./components/ScrollFloat";
import { SubscriptionPaywall } from "./components/SubscriptionPaywall";
import { TrialBanner } from "./components/TrialBanner";
import { Panel } from "./components/ui/Panel";
import { errorMessage } from "./errors";
import { initTelegram, setAccentColor } from "./telegram";
import type {
  Plan,
  Product,
  ProductInput,
  ProductPatch,
  Reservation,
  ReserveInput,
  Shop,
  Template,
  Variant,
} from "./types";

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showProductForm, setShowProductForm] = useState(false);
  const [showReservations, setShowReservations] = useState(false);
  const [clearingDemos, setClearingDemos] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    initTelegram();
    let mounted = true;

    async function load() {
      try {
        const [meResult, productsResult, templatesResult, reservationsResult, plansResult] =
          await Promise.all([
            api.getMe(),
            api.getProducts(),
            api.getTemplates(),
            api.getReservations(),
            api.getPlans(),
          ]);
        if (!mounted) return;
        setShop(meResult);
        setAccentColor(meResult.accent_color);
        setProducts(productsResult);
        setTemplates(templatesResult);
        setReservations(reservationsResult);
        setPlans(plansResult);
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

  async function handleUpdateProduct(productId: number, patch: ProductPatch) {
    try {
      const updated = await api.updateProduct(productId, patch);
      setProducts((prev) => prev.map((product) => (product.id === productId ? updated : product)));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося оновити товар"));
    }
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

  async function handleClearDemos() {
    setClearingDemos(true);
    try {
      await api.clearDemos();
      setProducts(await api.getProducts());
    } catch (err) {
      setError(errorMessage(err, "Не вдалося очистити приклади"));
    } finally {
      setClearingDemos(false);
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
  const writable = shop?.is_writable ?? false;
  const hasDemo = products.some((product) => product.is_demo);

  let lowStockCount = 0;
  let outOfStockCount = 0;
  for (const product of products) {
    for (const variant of product.variants) {
      if (variant.available === 0) outOfStockCount += 1;
      else if (variant.available <= variant.low_stock_threshold) lowStockCount += 1;
    }
  }
  const metricCards: MetricCardData[] = [
    { id: "products", title: "Товари", value: products.length, bgClass: "bg-green", textClass: "text-ink", icon: Package },
    { id: "reservations", title: "Резерви", value: reservations.length, bgClass: "bg-blue", textClass: "text-ink", icon: BookmarkCheck },
    { id: "low", title: "Мало", value: lowStockCount, bgClass: "bg-pink", textClass: "text-ink", icon: TriangleAlert },
    { id: "out", title: "Нема", value: outOfStockCount, bgClass: "bg-ink-2", textClass: "text-cream", icon: Ban },
  ];

  return (
    <>
      <AtmosphereBackground />
      <div className="app" ref={scrollContainerRef}>
        <Header shop={shop} scrollContainerRef={scrollContainerRef} />

        {error ? <p className="error-banner">{error}</p> : null}

        {shop?.status === "trial" && shop.trial_ends_at ? (
          <TrialBanner trialEndsAt={shop.trial_ends_at} />
        ) : null}

        {shop && !shop.is_writable ? (
          <>
            <p className="banner banner-readonly">Підписку призупинено, дані збережено</p>
            <SubscriptionPaywall
              plans={plans}
              role={shop.role}
              onCheckout={api.checkoutStars}
            />
          </>
        ) : null}

        {hasDemo ? (
          <DemoBanner
            canClear={shop?.role === "owner"}
            clearing={clearingDemos}
            onClear={handleClearDemos}
          />
        ) : null}

        {shop ? <MetricCarousel cards={metricCards} /> : null}

        <div className="toolbar">
          <input
            className="search-input"
            type="search"
            placeholder="Пошук товарів..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
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
          <Panel as="section" className="reservations-section">
            <ScrollFloat as="h2" className="section-title" scrollContainerRef={scrollContainerRef}>
              Резерви
            </ScrollFloat>
            <ReservationsPanel
              reservations={reservations}
              writable={writable}
              variantLabel={variantLabel}
              onRelease={handleRelease}
              onFulfill={handleFulfill}
            />
          </Panel>
        ) : null}

        <ScrollFloat as="h2" className="section-title" scrollContainerRef={scrollContainerRef}>
          Каталог
        </ScrollFloat>

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
                writable={writable}
                onRestock={handleRestock}
                onAdjust={handleAdjust}
                onUploadPhoto={handleUploadPhoto}
                onReserve={handleReserve}
                onUpdateProduct={handleUpdateProduct}
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
    </>
  );
}
