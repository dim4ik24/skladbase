import type { Shop } from "../types";

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
  if (
    shop.status === "trial" &&
    shop.trial_ends_at != null &&
    new Date(shop.trial_ends_at) > new Date()
  ) {
    return null;
  }
  return "free";
}

/** Human-readable label shown in SettingsScreen. Derived from effectivePlanCode. */
export function currentPlanLabel(shop: Shop): string {
  const code = effectivePlanCode(shop);
  if (code === null) return "Пробний період";
  if (code === "free") return "Безкоштовний";
  return code.charAt(0).toUpperCase() + code.slice(1);
}
