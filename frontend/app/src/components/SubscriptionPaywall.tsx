/**
 * SubscriptionPaywall — екран підписки/планів. Editorial sport-poster:
 * green-deep Panel, cream Card-картки планів (інверсія), NumberFlow-ціни,
 * VerticalCutReveal-заголовок. Sparkles прибрані (tsparticles → бандл схуд).
 * Контракт оплати (onCheckout → checkoutStars, openInvoice) — без змін.
 */
import { useState } from "react";
import { Check } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { errorMessage } from "../errors";
import { openInvoice } from "../telegram";
import type { Plan } from "../types";
import { Reveal } from "./Reveal";
import { Card, CardContent, CardHeader } from "./ui/Card";
import { Panel } from "./ui/Panel";
import { VerticalCutReveal } from "./VerticalCutReveal";

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

  const mostExpensive = plans.reduce<Plan | undefined>(
    (best, plan) => (Number(plan.price_uah) > Number(best?.price_uah ?? -1) ? plan : best),
    undefined,
  );
  const featuredCode = currentPlanCode ?? mostExpensive?.code;

  return (
    <Panel as="section" className="paywall p-6">
      <div className="mb-6 space-y-2 text-center">
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

      {error ? <p className="error-banner">{error}</p> : null}
      {fallbackLink ? (
        <p className="paywall-fallback">
          Відкрийте посилання в Telegram, щоб оплатити:{" "}
          <a href={fallbackLink} target="_blank" rel="noreferrer">
            {fallbackLink}
          </a>
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        {plans.map((plan, index) => {
          const isCurrent = plan.code === currentPlanCode;
          const isFeatured = plan.code === featuredCode;
          const features = planFeatures(plan.limits);

          return (
            <Reveal key={plan.code} index={index + 1}>
              <Card
                className={
                  isFeatured
                    ? "flex h-full flex-col ring-2 ring-green"
                    : "flex h-full flex-col"
                }
              >
                <CardHeader>
                  <h3 className="font-display text-xl font-semibold text-green-deep">{plan.name}</h3>
                  <div className="flex items-baseline gap-1">
                    <NumberFlow
                      value={Number(plan.price_uah)}
                      locales="uk-UA"
                      format={{ style: "currency", currency: "UAH", maximumFractionDigits: 0 }}
                      className="font-mono-price text-2xl font-bold text-green-deep"
                    />
                    <span className="text-sm text-green-deep/50">
                      /{plan.period === "year" ? "рік" : "міс"}
                    </span>
                  </div>
                  <p className="text-xs text-green-deep/45">{plan.price_stars} ⭐ через Telegram Stars</p>
                </CardHeader>

                <CardContent className="flex flex-1 flex-col">
                  {isCurrent ? (
                    <button
                      type="button"
                      disabled
                      className="mb-4 w-full rounded-xl bg-green/10 py-3 text-sm font-semibold text-green-deep/50"
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
                          ? "mb-4 w-full rounded-xl bg-green py-3 text-sm font-bold text-cream disabled:opacity-50"
                          : "mb-4 w-full rounded-xl border border-green/25 bg-green/8 py-3 text-sm font-semibold text-green-deep disabled:opacity-50"
                      }
                    >
                      {checkingOutCode === plan.code ? "Оформлюємо..." : "Оформити через Stars"}
                    </button>
                  )}

                  {features.length > 0 ? (
                    <ul className="flex flex-1 flex-col gap-2">
                      {features.map((feature) => (
                        <li key={feature} className="flex items-center gap-2 text-sm text-green-deep/70">
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
