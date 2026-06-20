/**
 * SubscriptionPaywall — екран підписки/планів. Інтегрує наданий
 * pricing-section (три плани, motion-reveal, NumberFlow-ціни, Sparkles-фон)
 * на місці попереднього текстового paywall: той самий тригер показу
 * (App.tsx: `shop && !shop.is_writable`), той самий контракт оплати
 * (`onCheckout` -> `api.checkoutStars`, openInvoice/fallbackLink/error —
 * без змін).
 *
 * Дані — лише реальні: назва/ціна (₴)/⭐ з `/api/plans`, фічі — з
 * `Plan.limits` (max_products/photos/integrations), без вигаданих рядків.
 * monthly/yearly-світч не показуємо: у наявних планах нема річних цін
 * (кожен `Plan` уже несе свій `period`, перемикач їх не подвоює).
 *
 * Sparkles — лінькво, density знижено (300, не 1800), вимкнено під
 * prefers-reduced-motion. Beams на цьому екрані призупиняється з App.tsx
 * (проп `suspended` в AtmosphereBackground) — один важкий ефект за раз.
 */
import { lazy, Suspense, useState } from "react";
import { Check } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { errorMessage } from "../errors";
import { openInvoice } from "../telegram";
import type { Plan } from "../types";
import { Reveal } from "./Reveal";
import { Card, CardContent, CardHeader } from "./ui/Card";
import { Panel } from "./ui/Panel";
import { VerticalCutReveal } from "./VerticalCutReveal";

const LazySparkles = lazy(() =>
  import("./ui/Sparkles").then((module) => ({ default: module.Sparkles })),
);

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

interface SubscriptionPaywallProps {
  plans: Plan[];
  role: "owner" | "manager";
  currentPlanCode?: string | null;
  onCheckout: (planCode: string) => Promise<{ invoice_link: string }>;
}

function planFeatures(limits: Record<string, unknown>): string[] {
  const features: string[] = [];
  const maxProducts = limits.max_products;
  if (maxProducts === null || maxProducts === undefined) {
    features.push("Необмежена кількість товарів");
  } else if (typeof maxProducts === "number") {
    features.push(`До ${maxProducts} товарів`);
  }
  if (limits.photos) features.push("Фото товарів");
  if (limits.integrations) features.push("Інтеграція з сайтом");
  return features;
}

export function SubscriptionPaywall({
  plans,
  role,
  currentPlanCode,
  onCheckout,
}: SubscriptionPaywallProps) {
  const [checkingOutCode, setCheckingOutCode] = useState<string | null>(null);
  const [fallbackLink, setFallbackLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canShowSparkles] = useState(() => !prefersReducedMotion());

  if (role === "manager") {
    return (
      <Panel as="section" className="paywall">
        <p className="status-text">
          Підписку призупинено. Оформлення доступне лише власнику магазину.
        </p>
      </Panel>
    );
  }

  async function handleCheckout(planCode: string) {
    setError(null);
    setFallbackLink(null);
    setCheckingOutCode(planCode);
    try {
      const { invoice_link } = await onCheckout(planCode);
      if (!openInvoice(invoice_link)) {
        setFallbackLink(invoice_link);
      }
    } catch (err) {
      setError(errorMessage(err, "Не вдалося оформити підписку"));
    } finally {
      setCheckingOutCode(null);
    }
  }

  // Підсвічуємо поточний активний план; якщо такого нема (тріал) —
  // найдорожчий тариф як рекомендований. Це лише вибір ОФОРМЛЕННЯ картки,
  // не вигадані дані — назви/ціни нижче завжди реальні з /api/plans.
  const mostExpensive = plans.reduce<Plan | undefined>(
    (best, plan) => (Number(plan.price_uah) > Number(best?.price_uah ?? -1) ? plan : best),
    undefined,
  );
  const featuredCode = currentPlanCode ?? mostExpensive?.code;

  return (
    <Panel as="section" className="paywall relative overflow-hidden p-6">
      <div className="pointer-events-none absolute inset-0 z-0" aria-hidden="true">
        <div
          className="absolute inset-x-0 top-0 h-full"
          style={{
            background: "radial-gradient(circle at 50% 0%, var(--blue) 0%, transparent 70%)",
            opacity: 0.35,
            mixBlendMode: "screen",
          }}
        />
        {canShowSparkles ? (
          <Suspense fallback={null}>
            <LazySparkles
              density={300}
              color="#F5F4ED"
              speed={0.4}
              opacity={0.5}
              className="absolute inset-0 h-full w-full"
            />
          </Suspense>
        ) : null}
      </div>

      <div className="relative z-10 mb-6 space-y-2 text-center">
        <h2 className="section-title">
          <VerticalCutReveal
            splitBy="words"
            staggerDuration={0.12}
            staggerFrom="first"
            containerClassName="justify-center"
          >
            Оберіть тариф
          </VerticalCutReveal>
        </h2>
        <Reveal index={0} as="p" className="text-sm text-cream/60">
          Оплата через Telegram Stars — без банківської картки.
        </Reveal>
      </div>

      {error ? <p className="error-banner relative z-10">{error}</p> : null}
      {fallbackLink ? (
        <p className="paywall-fallback relative z-10">
          Відкрийте посилання в Telegram, щоб оплатити:{" "}
          <a href={fallbackLink} target="_blank" rel="noreferrer">
            {fallbackLink}
          </a>
        </p>
      ) : null}

      <div className="relative z-10 grid gap-4 sm:grid-cols-3">
        {plans.map((plan, index) => {
          const isCurrent = plan.code === currentPlanCode;
          const isFeatured = plan.code === featuredCode;
          const features = planFeatures(plan.limits);

          return (
            <Reveal key={plan.code} index={index + 1}>
              <Card
                className={
                  isFeatured
                    ? "flex h-full flex-col shadow-[0_0_50px_-12px_var(--green)] ring-1 ring-[var(--green)]/40"
                    : "flex h-full flex-col"
                }
              >
                <CardHeader>
                  <h3 className="font-display text-xl font-semibold text-cream">{plan.name}</h3>
                  <div className="flex items-baseline gap-1">
                    <NumberFlow
                      value={Number(plan.price_uah)}
                      locales="uk-UA"
                      format={{ style: "currency", currency: "UAH", maximumFractionDigits: 0 }}
                      className="font-mono-price text-2xl font-bold text-cream"
                    />
                    <span className="text-sm text-cream/50">
                      /{plan.period === "year" ? "рік" : "міс"}
                    </span>
                  </div>
                  <p className="text-xs text-cream/45">{plan.price_stars} ⭐ через Telegram Stars</p>
                </CardHeader>

                <CardContent className="flex flex-1 flex-col">
                  {isCurrent ? (
                    <button
                      type="button"
                      disabled
                      className="mb-4 w-full rounded-xl bg-ink-2 py-3 text-sm font-semibold text-cream/60"
                    >
                      Поточний план
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={checkingOutCode === plan.code}
                      onClick={() => handleCheckout(plan.code)}
                      className={
                        isFeatured
                          ? "mb-4 w-full rounded-xl bg-green py-3 text-sm font-semibold text-ink disabled:opacity-50"
                          : "mb-4 w-full rounded-xl border border-[var(--line)] bg-ink-2 py-3 text-sm font-semibold text-cream disabled:opacity-50"
                      }
                    >
                      {checkingOutCode === plan.code ? "Оформлюємо..." : "Оформити через Stars"}
                    </button>
                  )}

                  {features.length > 0 ? (
                    <ul className="flex flex-1 flex-col gap-2">
                      {features.map((feature) => (
                        <li key={feature} className="flex items-center gap-2 text-sm text-cream/70">
                          <Check size={14} className="shrink-0 text-green" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </CardContent>
              </Card>
            </Reveal>
          );
        })}
      </div>
    </Panel>
  );
}
