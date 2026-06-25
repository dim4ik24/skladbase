/**
 * SubscriptionPaywall — блокувальна модалка підписки (portal, bottom-sheet).
 * Показується ТІЛЬКИ коли !shop.is_writable (тріал і активна підписка пропускаються).
 * Без кнопки закриття: paywall не закривається без оплати.
 */
import { createPortal } from "react-dom";
import { useState } from "react";
import { Check, Lock } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { motion, useReducedMotion } from "motion/react";
import { errorMessage } from "../errors";
import { openInvoice } from "../telegram";
import type { Plan } from "../types";
import { Reveal } from "./Reveal";

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
  const prefersReducedMotion = useReducedMotion();

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

  const sheetContent =
    role === "manager" ? (
      <div className="flex flex-col items-center text-center py-6 gap-4">
        <div className="rounded-full bg-cream/10 p-4">
          <Lock size={32} className="text-cream/60" aria-hidden="true" />
        </div>
        <div>
          <h2
            className="font-display text-xl font-bold text-cream mb-2"
            style={{ textWrap: "balance" } as React.CSSProperties}
          >
            Підписку призупинено
          </h2>
          <p className="text-sm text-cream/60">
            Оформлення доступне лише власнику магазину.
          </p>
        </div>
      </div>
    ) : (
      <>
        <div className="mb-6 text-center">
          <div className="flex justify-center mb-4">
            <div className="rounded-full bg-cream/10 p-4">
              <Lock size={28} className="text-cream/70" aria-hidden="true" />
            </div>
          </div>
          <h2
            className="font-display text-2xl font-bold text-cream mb-2"
            style={{ textWrap: "balance" } as React.CSSProperties}
          >
            Оберіть тариф
          </h2>
          <p className="text-sm text-cream/60">
            Пробний період завершився — оберіть план, щоб продовжити роботу.
          </p>
        </div>

        {error ? <p className="error-banner">{error}</p> : null}
        {fallbackLink ? (
          <p className="paywall-fallback">
            Відкрийте посилання в Telegram:{" "}
            <a href={fallbackLink} target="_blank" rel="noreferrer">
              {fallbackLink}
            </a>
          </p>
        ) : null}

        <div className="flex flex-col gap-3">
          {plans.map((plan, index) => {
            const isCurrent = plan.code === currentPlanCode;
            const isFeatured = plan.code === featuredCode;
            const features = planFeatures(plan.limits);

            return (
              <Reveal key={plan.code} index={index}>
                <div
                  className={`rounded-2xl bg-cream p-4${isFeatured ? " ring-2 ring-green" : ""}`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <h3 className="font-display text-base font-semibold text-green-deep leading-tight">
                          {plan.name}
                        </h3>
                        {isFeatured && !isCurrent ? (
                          <span className="rounded-full bg-green px-2 py-0.5 text-[10px] font-bold text-cream shrink-0">
                            Рекомендовано
                          </span>
                        ) : null}
                      </div>
                      <p className="font-mono-price text-[11px] text-green-deep/45">
                        або {plan.price_stars}&nbsp;⭐
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <NumberFlow
                        value={Number(plan.price_uah)}
                        locales="uk-UA"
                        format={{ style: "currency", currency: "UAH", maximumFractionDigits: 0 }}
                        className="font-display text-3xl font-bold text-green-deep block"
                      />
                      <p className="font-mono-price text-[11px] text-green-deep/50 mt-0.5">
                        /{plan.period === "year" ? "рік" : "міс"}
                      </p>
                    </div>
                  </div>

                  {features.length > 0 ? (
                    <ul className="flex flex-col gap-1.5 mb-3">
                      {features.map((feature) => (
                        <li
                          key={feature}
                          className="flex items-center gap-2 text-sm text-green-deep/70"
                        >
                          <Check size={13} className="shrink-0 text-green" aria-hidden="true" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}

                  {isCurrent ? (
                    <button
                      type="button"
                      disabled
                      className="w-full rounded-xl bg-green/10 py-2.5 text-sm font-semibold text-green-deep/50"
                    >
                      Поточний план
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={checkingOutCode === plan.code}
                      onClick={() => void handleCheckout(plan.code)}
                      className={
                        isFeatured
                          ? "w-full rounded-xl bg-green py-2.5 text-sm font-bold text-cream transition-opacity duration-150 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green disabled:opacity-50"
                          : "w-full rounded-xl border border-green/30 py-2.5 text-sm font-semibold text-green-deep transition-opacity duration-150 hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green disabled:opacity-50"
                      }
                    >
                      {checkingOutCode === plan.code ? "Оформлюємо…" : "Оформити через Stars"}
                    </button>
                  )}
                </div>
              </Reveal>
            );
          })}
        </div>
      </>
    );

  return createPortal(
    <div
      className="paywall-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Оберіть тариф"
    >
      <motion.div
        className="paywall-sheet"
        initial={{ y: prefersReducedMotion ? 0 : "100%" }}
        animate={{ y: 0 }}
        transition={
          prefersReducedMotion
            ? { duration: 0 }
            : { type: "spring", bounce: 0.08, duration: 0.45 }
        }
      >
        {sheetContent}
      </motion.div>
    </div>,
    document.body,
  );
}
