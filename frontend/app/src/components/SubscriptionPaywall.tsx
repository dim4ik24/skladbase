import { useState } from "react";
import { errorMessage } from "../errors";
import { openInvoice } from "../telegram";
import type { Plan } from "../types";

interface SubscriptionPaywallProps {
  plans: Plan[];
  role: "owner" | "manager";
  onCheckout: (planCode: string) => Promise<{ invoice_link: string }>;
}

export function SubscriptionPaywall({ plans, role, onCheckout }: SubscriptionPaywallProps) {
  const [checkingOutCode, setCheckingOutCode] = useState<string | null>(null);
  const [fallbackLink, setFallbackLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (role === "manager") {
    return (
      <section className="paywall">
        <p className="status-text">
          Підписку призупинено. Оформлення доступне лише власнику магазину.
        </p>
      </section>
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

  return (
    <section className="paywall">
      <h2>Оберіть тариф</h2>
      {error ? <p className="error-banner">{error}</p> : null}
      {fallbackLink ? (
        <p className="paywall-fallback">
          Відкрийте посилання в Telegram, щоб оплатити:{" "}
          <a href={fallbackLink} target="_blank" rel="noreferrer">
            {fallbackLink}
          </a>
        </p>
      ) : null}
      <ul className="plan-list">
        {plans.map((plan) => (
          <li className="plan-row" key={plan.code}>
            <span className="plan-name">{plan.name}</span>
            <span className="plan-price">{plan.price_stars} ⭐</span>
            <button
              type="button"
              disabled={checkingOutCode === plan.code}
              onClick={() => handleCheckout(plan.code)}
            >
              {checkingOutCode === plan.code ? "Оформлюємо..." : "Оформити через Stars"}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
