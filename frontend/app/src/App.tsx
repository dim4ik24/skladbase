import { Ban, BookmarkCheck, Package, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "./api";
import { ApiError } from "./api";
import { AtmosphereBackground } from "./components/background/AtmosphereBackground";
import { BottomTabBar } from "./components/BottomTabBar";
import { DemoBanner } from "./components/DemoBanner";
import { Header } from "./components/Header";
import type { MetricCardData } from "./components/MetricCarousel";
import { SubscriptionPaywall } from "./components/SubscriptionPaywall";
import { TrialBanner } from "./components/TrialBanner";
import { UpgradePrompt } from "./components/UpgradePrompt";
import { errorMessage } from "./errors";
import { DashboardScreen } from "./screens/DashboardScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import { SkladScreen } from "./screens/SkladScreen";
import { effectivePlanCode, isLiveTrial } from "./lib/planStatus";
import { initTelegram, setAccentColor } from "./telegram";
import type {
  Plan,
  Product,
  ProductInput,
  ProductPatch,
  Reservation,
  ReserveInput,
  Shop,
  TabId,
  Template,
  Variant,
} from "./types";

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearingDemos, setClearingDemos] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [showPaywall, setShowPaywall] = useState(false);
  const [upgradePrompt, setUpgradePrompt] = useState<{ message: string } | null>(null);
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
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      } else {
        setError(errorMessage(err, "Не вдалося поповнити залишок"));
      }
    }
  }

  async function handleAdjust(variantId: number, newOnHand: number) {
    try {
      applyVariantUpdate(await api.adjust(variantId, newOnHand));
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      } else {
        setError(errorMessage(err, "Не вдалося оновити залишок"));
      }
    }
  }

  async function handleCreateProduct(payload: ProductInput): Promise<Product> {
    try {
      const product = await api.createProduct(payload);
      setProducts((prev) => [...prev, product]);
      return product;
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      }
      throw err;
    }
  }

  async function handleUpdateProduct(productId: number, patch: ProductPatch) {
    try {
      const updated = await api.updateProduct(productId, patch);
      setProducts((prev) => prev.map((p) => (p.id === productId ? updated : p)));
    } catch (err) {
      setError(errorMessage(err, "Не вдалося оновити товар"));
    }
  }

  async function handleUploadPhoto(variantId: number, file: File) {
    try {
      applyVariantUpdate(await api.uploadVariantPhoto(variantId, file));
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      } else {
        throw err;
      }
    }
  }

  async function handleUploadProductPhoto(productId: number, file: File): Promise<void> {
    try {
      const photo = await api.uploadProductPhoto(productId, file);
      setProducts((prev) =>
        prev.map((p) =>
          p.id === productId
            ? { ...p, photos: [...p.photos, photo].sort((a, b) => a.position - b.position) }
            : p,
        ),
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      }
      throw err;
    }
  }

  async function handleDeleteProductPhoto(productId: number, photoId: number): Promise<void> {
    await api.deleteProductPhoto(productId, photoId);
    setProducts((prev) =>
      prev.map((p) =>
        p.id === productId
          ? { ...p, photos: p.photos.filter((ph) => ph.id !== photoId) }
          : p,
      ),
    );
  }

  async function handleUpdateShopName(name: string): Promise<{ shop_name: string; logo_url: string | null }> {
    const result = await api.updateShopProfile(name);
    setShop((prev) => prev ? { ...prev, shop_name: result.shop_name, logo_url: result.logo_url } : prev);
    return result;
  }

  async function handleUploadShopLogo(file: File): Promise<void> {
    const result = await api.uploadShopLogo(file);
    setShop((prev) => prev ? { ...prev, logo_url: result.logo_url } : prev);
  }

  async function handleDeleteShopLogo(): Promise<void> {
    await api.deleteShopLogo();
    setShop((prev) => prev ? { ...prev, logo_url: null } : prev);
  }

  async function handleReserve(variantId: number, payload: ReserveInput) {
    try {
      const reservation = await api.reserve(variantId, payload);
      const variant = products
        .flatMap((product) => product.variants)
        .find((v) => v.id === variantId);
      const reserved = (variant?.reserved ?? 0) + reservation.qty;
      const onHand = variant?.on_hand ?? 0;
      patchVariant(variantId, { reserved, available: onHand - reserved });
      setReservations((prev) => [reservation, ...prev]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setUpgradePrompt({ message: err.detail });
      } else {
        throw err;
      }
    }
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

  function handleFrozenAction() {
    setUpgradePrompt({ message: "Цей товар заморожено. Оформіть тариф, щоб редагувати." });
  }

  const writable = shop?.is_writable ?? false;
  const photosAllowed = shop?.limits["photos"] === true;
  const hasDemo = products.some((p) => p.is_demo);
  const maxProducts = shop?.max_products ?? null;
  const activeCount = shop?.active_count ?? 0;
  const atLimit = maxProducts !== null && activeCount >= maxProducts;

  let lowStockCount = 0;
  let outOfStockCount = 0;
  for (const product of products) {
    for (const variant of product.variants) {
      if (variant.available === 0) outOfStockCount += 1;
      else if (variant.available <= variant.low_stock_threshold) lowStockCount += 1;
    }
  }

  const metricCards: MetricCardData[] = [
    {
      id: "products",
      title: "Товари",
      value: products.length,
      iconBg: "bg-pastel-mint",
      iconColor: "text-green-deep",
      icon: Package,
    },
    {
      id: "reservations",
      title: "Резерви",
      value: reservations.length,
      iconBg: "bg-pastel-lavender",
      iconColor: "text-green-deep",
      icon: BookmarkCheck,
    },
    {
      id: "low",
      title: "Мало",
      value: lowStockCount,
      iconBg: "bg-pastel-rose",
      iconColor: "text-pink",
      icon: TriangleAlert,
    },
    {
      id: "out",
      title: "Нема",
      value: outOfStockCount,
      iconBg: "bg-pastel-peach",
      iconColor: "text-text-soft",
      icon: Ban,
    },
  ];

  return (
    <>
      <AtmosphereBackground />
      <div className="app" ref={scrollContainerRef}>
        <Header shop={shop} scrollContainerRef={scrollContainerRef} />

        {error ? <p className="error-banner">{error}</p> : null}

        {shop && isLiveTrial(shop) ? (
          <TrialBanner shop={shop} />
        ) : null}

        {hasDemo ? (
          <DemoBanner
            canClear={shop?.role === "owner"}
            clearing={clearingDemos}
            onClear={handleClearDemos}
          />
        ) : null}

        {activeTab === "sklad" ? (
          <SkladScreen
            products={products}
            templates={templates}
            reservations={reservations}
            loading={loading}
            writable={writable}
            atLimit={atLimit}
            maxProducts={maxProducts}
            activeCount={activeCount}
            variantLabel={variantLabel}
            onRestock={handleRestock}
            onAdjust={handleAdjust}
            onUploadPhoto={handleUploadPhoto}
            onReserve={handleReserve}
            onRelease={handleRelease}
            onFulfill={handleFulfill}
            onCreateProduct={handleCreateProduct}
            onUpdateProduct={handleUpdateProduct}
            onFrozenAction={handleFrozenAction}
            onAddAtLimit={() =>
              setUpgradePrompt({
                message: `Ліміт плану: ${maxProducts} товарів. Оформіть тариф для розширення.`,
              })
            }
            scrollContainerRef={scrollContainerRef}
            isOwner={shop?.role === "owner"}
            onTemplateAdded={(t) => setTemplates((prev) => [...prev, t])}
            photosAllowed={photosAllowed}
            onUploadProductPhoto={handleUploadProductPhoto}
            onDeleteProductPhoto={handleDeleteProductPhoto}
          />
        ) : activeTab === "dashboard" ? (
          <DashboardScreen
            shop={shop}
            loading={loading}
            metricCards={metricCards}
            reservations={reservations}
            variantLabel={variantLabel}
            onRelease={handleRelease}
            onFulfill={handleFulfill}
            scrollContainerRef={scrollContainerRef}
          />
        ) : (
          <SettingsScreen
            shop={shop}
            onOpenPaywall={() => setShowPaywall(true)}
            onUpdateShopName={handleUpdateShopName}
            onUploadShopLogo={handleUploadShopLogo}
            onDeleteShopLogo={handleDeleteShopLogo}
          />
        )}
      </div>

      <BottomTabBar active={activeTab} onChange={setActiveTab} />

      {upgradePrompt ? (
        <UpgradePrompt
          message={upgradePrompt.message}
          onOpenPaywall={() => setShowPaywall(true)}
          onClose={() => setUpgradePrompt(null)}
        />
      ) : null}

      {showPaywall && shop ? (
        <SubscriptionPaywall
          plans={plans}
          role={shop.role}
          currentPlanCode={effectivePlanCode(shop)}
          onCheckout={api.checkoutStars}
          onDismiss={() => setShowPaywall(false)}
        />
      ) : null}
    </>
  );
}
