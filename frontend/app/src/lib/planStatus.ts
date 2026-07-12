import type { TFunction } from "i18next";
import type { Shop } from "../types";

/** Single source of truth: trial is live only if status=trial AND ends in the future. */
export function isLiveTrial(shop: Shop): boolean {
  return (
    shop.status === "trial" &&
    shop.trial_ends_at != null &&
    new Date(shop.trial_ends_at) > new Date()
  );
}

/** Days remaining in a live trial; 0 if trial is not live. */
export function trialDaysLeft(shop: Shop): number {
  if (!isLiveTrial(shop)) return 0;
  const ms = new Date(shop.trial_ends_at!).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (24 * 60 * 60 * 1000)));
}

/**
 * Returns the plan code that represents the user's current effective plan:
 *   - active paid subscription → the actual plan_code
 *   - live trial               → null  (trial is not a plan; paywall shows no badge)
 *   - everything else          → "free" (expired, expired-trial, free-tier)
 *
 * Used by SettingsScreen (currentPlanLabel) and App.tsx (paywall currentPlanCode).
 * Keep this as the single source of truth so both UIs stay in sync.
 */
export function effectivePlanCode(shop: Shop): string | null {
  if (
    shop.plan_code != null &&
    shop.plan_code !== "free" &&
    (shop.status === "active" || shop.status === "canceled" || shop.status === "past_due")
  ) {
    return shop.plan_code;
  }
  if (isLiveTrial(shop)) {
    return null;
  }
  return "free";
}

/** Human-readable label shown in SettingsScreen. Derived from effectivePlanCode. */
export function currentPlanLabel(shop: Shop, t: TFunction): string {
  const code = effectivePlanCode(shop);
  if (code === null) return t("settings.subscription.planTrial");
  if (code === "free") return t("settings.subscription.planFree");
  return code.charAt(0).toUpperCase() + code.slice(1);
}
