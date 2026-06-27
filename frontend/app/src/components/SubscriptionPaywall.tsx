/**
 * SubscriptionPaywall — напівблокувальна модалка підписки (light fintech).
 * Монтується тільки коли !shop.is_writable. Першим показом — розгорнута
 * (portal overlay), але закривається кнопкою «Переглянути склад».
 * У згорнутому стані — стійкий банер з кнопкою «Оформити».
 */
import { createPortal } from "react-dom";
import { useState } from "react";
import { Check, Lock, X } from "lucide-react";
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
  onDismiss?: () => void;
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
  onDismiss,
}: SubscriptionPaywallProps) {
  const [isOpen, setIsOpen] = useState(true);
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

  // ── Collapsed banner ────────────────────────────────────────────────
  if (!isOpen) {
    return (
      <div className="banner banner-paywall" role="status">
        <span>Підписку призупинено — дії заблоковано</span>
        {role === "owner" ? (
          <button
            type="button"
            onClick={() => setIsOpen(true)}
            className="rounded-xl bg-green px-3 py-1.5 text-xs font-bold text-white transition-opacity duration-150 hover:opacity-85"
          >
            Оформити
          </button>
        ) : null}
      </div>
    );
  }

  // ── Manager content (no plans, no payment) ──────────────────────────
  const managerContent = (
    <div className="flex flex-col items-center text-center py-8 gap-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-pastel-mint">
        <Lock size={26} className="text-green-deep" aria-hidden="true" />
      </div>
      <div>
        <h2 className="font-sans text-xl font-bold text-text mb-2 text-balance">
          Підписку призупинено
        </h2>
        <p className="text-sm text-text-soft">
          Оформлення доступне лише власнику магазину.
        </p>
      </div>
    </div>
  );

  // ── Owner content (plan cards) ──────────────────────────────────────
  const ownerContent = (
    <>
      <div className="mb-6 text-center">
        <div className="flex justify-center mb-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-pastel-mint">
            <Lock size={26} className="text-green-deep" aria-hidden="true" />
          </div>
        </div>
        <h2 className="font-sans text-xl font-bold text-text mb-1.5 text-balance">
          Оберіть тариф
        </h2>
        <p className="text-sm text-text-soft">
          Пробний період завершився — оберіть план, щоб продовжити.
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
          const isFree = plan.price_stars === 0 || Number(plan.price_uah) === 0;
          const features = planFeatures(plan.limits);

          return (
            <Reveal key={plan.code} index={index}>
              <div
                className={`rounded-2xl p-4 ${
                  isFeatured
                    ? "bg-surface ring-2 ring-green shadow-[var(--shadow-card)]"
                    : "bg-bg"
                }`}
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <h3 className="font-sans text-base font-bold text-text leading-tight">
                        {plan.name}
                      </h3>
                      {isCurrent ? (
                        <span className="rounded-full bg-[var(--state-ok)] px-2 py-0.5 text-[10px] font-bold text-green-deep shrink-0">
                          Поточний
                        </span>
                      ) : isFeatured ? (
                        <span className="rounded-full bg-green px-2 py-0.5 text-[10px] font-bold text-white shrink-0">
                          Рекомендовано
                        </span>
                      ) : null}
                    </div>
                    {!isFree ? (
                      <p className="font-mono-price text-[11px] text-text-soft">
                        або {plan.price_stars}&nbsp;⭐
                      </p>
                    ) : null}
                  </div>
                  <div className="text-right shrink-0">
                    <NumberFlow
                      value={Number(plan.price_uah)}
                      locales="uk-UA"
                      format={{ style: "currency", currency: "UAH", maximumFractionDigits: 0 }}
                      className="font-sans text-3xl font-bold text-text block"
                    />
                    <p className="font-mono-price text-[11px] text-text-soft mt-0.5">
                      /{plan.period === "year" ? "рік" : "міс"}
                    </p>
                  </div>
                </div>

                {features.length > 0 ? (
                  <ul className="flex flex-col gap-1.5 mb-3">
                    {features.map((feature) => (
                      <li
                        key={feature}
                        className="flex items-center gap-2 text-sm text-text-soft"
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
                    className="w-full rounded-xl bg-bg py-2.5 text-sm font-semibold text-text-soft"
                  >
                    Поточний план
                  </button>
                ) : isFree ? (
                  <button
                    type="button"
                    disabled
                    className="w-full rounded-xl bg-bg py-2.5 text-sm font-semibold text-text-soft"
                  >
                    Безкоштовний
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={checkingOutCode === plan.code}
                    onClick={() => void handleCheckout(plan.code)}
                    className={
                      isFeatured
                        ? "w-full rounded-xl bg-green py-2.5 text-sm font-bold text-white shadow-[var(--shadow-fab)] transition-opacity duration-150 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green disabled:opacity-50"
                        : "w-full rounded-xl border border-[var(--line)] py-2.5 text-sm font-semibold text-text transition-opacity duration-150 hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green disabled:opacity-50"
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

  // ── Expanded modal (portal) ─────────────────────────────────────────
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
        <div className="flex justify-end mb-3">
          <button
            type="button"
            aria-label="Переглянути склад"
            onClick={() => (onDismiss ? onDismiss() : setIsOpen(false))}
            className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-text-soft transition-colors duration-150 hover:bg-bg hover:text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green"
          >
            <X size={13} aria-hidden="true" />
            Переглянути склад
          </button>
        </div>

        {role === "manager" ? managerContent : ownerContent}
      </motion.div>
    </div>,
    document.body,
  );
}
