import { useEffect, useState } from "react";
import * as api from "./api";
import { ApiError } from "./api";
import { Header } from "./components/Header";
import { ProductCard } from "./components/ProductCard";
import { initTelegram, setAccentColor } from "./telegram";
import type { Product, Shop, Variant } from "./types";

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

export default function App() {
  const [shop, setShop] = useState<Shop | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    initTelegram();
    let mounted = true;

    async function load() {
      try {
        const [meResult, productsResult] = await Promise.all([
          api.getMe(),
          api.getProducts(),
        ]);
        if (!mounted) return;
        setShop(meResult);
        setAccentColor(meResult.accent_color);
        setProducts(productsResult);
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

  const filteredProducts = products.filter((product) =>
    product.name.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="app">
      <Header shop={shop} />

      {error ? <p className="error-banner">{error}</p> : null}

      <input
        className="search-input"
        type="search"
        placeholder="Пошук товарів..."
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        aria-label="Пошук товарів"
      />

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
            />
          ))}
        </div>
      )}
    </div>
  );
}
