import { useState } from "react";
import type { FormEvent } from "react";
import { errorMessage } from "../errors";

interface OnboardingScreenProps {
  onCreateShop: (name: string) => Promise<void>;
}

export function OnboardingScreen({ onCreateShop }: OnboardingScreenProps) {
  const [name, setName] = useState("");
  const [nameInvalid, setNameInvalid] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setNameInvalid(true);
      setError("Вкажіть назву магазину");
      return;
    }
    setNameInvalid(false);
    setError(null);
    setCreating(true);
    try {
      await onCreateShop(name.trim());
    } catch (err) {
      setError(errorMessage(err, "Не вдалося створити магазин"));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="onboarding-screen">
      <div className="glass-card onboarding-card rounded-[20px] p-6 shadow-[var(--shadow-card)]">
        <h1 className="text-xl font-bold text-text mb-1">Ласкаво просимо в SkladBase</h1>
        <p className="text-sm text-text-soft mb-4">
          Створіть свій магазин, щоб почати вести облік товарів.
        </p>

        {error ? <p className="error-banner">{error}</p> : null}

        <form onSubmit={(e) => void handleSubmit(e)}>
          <label className="form-field">
            <span>Назва магазину</span>
            <input
              type="text"
              aria-label="Назва магазину"
              className={nameInvalid ? "input-error" : undefined}
              value={name}
              maxLength={120}
              disabled={creating}
              onChange={(e) => {
                setName(e.target.value);
                setNameInvalid(false);
              }}
            />
          </label>

          <button
            type="submit"
            disabled={creating}
            className="w-full rounded-2xl py-2.5 text-sm font-bold text-white disabled:opacity-50"
            style={{
              background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
              boxShadow: "var(--shadow-cta)",
            }}
          >
            {creating ? "Створюємо…" : "Створити магазин"}
          </button>
        </form>

        <p className="text-xs text-text-soft mt-4 text-center">
          Маєте запрошення від власника магазину? Просто перейдіть за
          посиланням-запрошенням — і ви приєднаєтесь до його команди.
        </p>
      </div>
    </div>
  );
}
