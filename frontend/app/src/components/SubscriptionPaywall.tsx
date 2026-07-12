import { createPortal } from "react-dom";
import { useState } from "react";
import { Check, Lock, X } from "lucide-react";
import NumberFlow from "@number-flow/react";
import { motion, useReducedMotion } from "motion/react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { errorMessage } from "../errors";
import { openInvoice } from "../telegram";
import type { Plan } from "../types";
import { Reveal } from "./Reveal";

interface SubscriptionPaywallProps {
  plans: Plan[];
  role: "owner" | "manager";
  currentPlanCode?: string | null;
  onCheckout: (planCode: string) => Promise<{ invoice_link: string }>;
  onRedeemPromo: (code: string) => Promise<void>;
  onDismiss?: () => void;
}

function planFeatures(limits: Record<string, unknown>, t: TFunction): string[] {
  const features: string[] = [];
  const maxProducts = limits.max_products;
  if (maxProducts === null || maxProducts === undefined) {
    features.push(t("paywall.unlimitedProducts"));
  } else if (typeof maxProducts === "number") {
    features.push(t("paywall.maxProducts", { count: maxProducts }));
  }
  if (limits.photos) features.push(t("paywall.photosFeature"));
  if (limits.integrations) features.push(t("paywall.integrationsFeature"));
  return features;
}

export function SubscriptionPaywall({
  plans,
  role,
  currentPlanCode,
  onCheckout,
  onRedeemPromo,
  onDismiss,
}: SubscriptionPaywallProps) {
  const { t } = useTranslation();
  const [checkingOutCode, setCheckingOutCode] = useState<string | null>(null);
  const [fallbackLink, setFallbackLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [promoCode, setPromoCode] = useState("");
  const [redeemingPromo, setRedeemingPromo] = useState(false);
  const [promoError, setPromoError] = useState<string | null>(null);
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
      setError(errorMessage(err, t("paywall.checkoutFailed")));
    } finally {
      setCheckingOutCode(null);
    }
  }

  async function handleRedeemPromo() {
    const trimmed = promoCode.trim();
    if (!trimmed) return;
    setPromoError(null);
    setRedeemingPromo(true);
    try {
      await onRedeemPromo(trimmed);
      // Успіх закриває paywall (App.tsx) — тут нічого прибирати не треба.
    } catch (err) {
      setPromoError(errorMessage(err, t("paywall.promoFailed")));
    } finally {
      setRedeemingPromo(false);
    }
  }

  const mostExpensive = plans.reduce<Plan | undefined>(
    (best, plan) => (Number(plan.price_uah) > Number(best?.price_uah ?? -1) ? plan : best),
    undefined,
  );
  const featuredCode = currentPlanCode ?? mostExpensive?.code;

  // ── Manager content (no plans, no payment) ──────────────────────────
  const managerContent = (
    <div className="flex flex-col items-center text-center py-8 gap-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-pastel-mint">
        <Lock size={26} className="text-green-deep" aria-hidden="true" />
      </div>
      <div>
        <h2 className="font-sans text-xl font-bold text-text mb-2 text-balance">
          {t("paywall.managerTitle")}
        </h2>
        <p className="text-sm text-text-soft">{t("paywall.managerSubtitle")}</p>
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
          {t("paywall.title")}
        </h2>
        <p className="text-sm text-text-soft">{t("paywall.subtitle")}</p>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}
      {fallbackLink ? (
        <p className="paywall-fallback">
          {t("paywall.openInTelegram")}{" "}
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
          const features = planFeatures(plan.limits, t);

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
                          {t("paywall.current")}
                        </span>
                      ) : isFeatured ? (
                        <span className="rounded-full bg-green px-2 py-0.5 text-[10px] font-bold text-white shrink-0">
                          {t("paywall.recommended")}
                        </span>
                      ) : null}
                    </div>
                    {!isFree ? (
                      <p className="font-mono-price text-[11px] text-text-soft">
                        {t("paywall.orStars", { stars: plan.price_stars })}
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
                      /{plan.period === "year" ? t("paywall.periodYear") : t("paywall.periodMonth")}
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
                    {t("paywall.currentPlanButton")}
                  </button>
                ) : isFree ? (
                  <button
                    type="button"
                    disabled
                    className="w-full rounded-xl bg-bg py-2.5 text-sm font-semibold text-text-soft"
                  >
                    {t("paywall.freeButton")}
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
                    {checkingOutCode === plan.code
                      ? t("paywall.checkingOut")
                      : t("paywall.checkoutButton")}
                  </button>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-[var(--line)]">
        <label className="form-field">
          <span>{t("paywall.promoLabel")}</span>
          <input
            type="text"
            value={promoCode}
            onChange={(e) => setPromoCode(e.target.value)}
            placeholder={t("paywall.promoPlaceholder")}
            aria-label={t("paywall.promoLabel")}
          />
        </label>
        {promoError ? <p className="error-banner">{promoError}</p> : null}
        <button
          type="button"
          disabled={redeemingPromo || !promoCode.trim()}
          onClick={() => void handleRedeemPromo()}
          className="mt-2 w-full rounded-xl border border-[var(--line)] py-2.5 text-sm font-semibold text-text transition-opacity duration-150 hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green disabled:opacity-50"
        >
          {redeemingPromo ? t("paywall.redeeming") : t("paywall.redeemButton")}
        </button>
      </div>
    </>
  );

  // ── Modal (portal) ─────────────────────────────────────────────────
  return createPortal(
    <div
      className="paywall-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={t("paywall.title")}
      onClick={onDismiss}
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
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-end mb-3">
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={onDismiss}
            className="flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-text-soft transition-colors duration-150 hover:bg-bg hover:text-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green"
          >
            <X size={13} aria-hidden="true" />
            {t("common.close")}
          </button>
        </div>

        {role === "manager" ? managerContent : ownerContent}
      </motion.div>
    </div>,
    document.body,
  );
}
