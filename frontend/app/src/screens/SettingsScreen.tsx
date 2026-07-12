import { useRef, useState } from "react";
import type { RefObject } from "react";
import { currentPlanLabel } from "../lib/planStatus";
import { errorMessage } from "../errors";
import { NpKeySection } from "../components/NpKeySection";
import { TeamSection } from "../components/TeamSection";
import type { Shop } from "../types";

interface SettingsScreenProps {
  shop: Shop | null;
  onOpenPaywall: () => void;
  onUpdateShopName: (name: string) => Promise<{ shop_name: string; logo_url: string | null }>;
  onUploadShopLogo: (file: File) => Promise<void>;
  onDeleteShopLogo: () => Promise<void>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
}

const STATUS_LABELS: Record<string, { label: string; colorClass: string }> = {
  trial: { label: "Тріал", colorClass: "text-green-deep" },
  active: { label: "Активна", colorClass: "text-green-deep" },
  past_due: { label: "Прострочена", colorClass: "text-[#b0460e]" },
  canceled: { label: "Скасована", colorClass: "text-text-soft" },
  expired: { label: "Закінчилась", colorClass: "text-[#b0460e]" },
};

const COMING_SOON = ["Мова", "Підключення акаунтів"];

function ShopProfileSection({
  shop,
  onUpdateShopName,
  onUploadShopLogo,
  onDeleteShopLogo,
}: {
  shop: Shop;
  onUpdateShopName: (name: string) => Promise<{ shop_name: string; logo_url: string | null }>;
  onUploadShopLogo: (file: File) => Promise<void>;
  onDeleteShopLogo: () => Promise<void>;
}) {
  const [name, setName] = useState(shop.shop_name);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSaveName() {
    if (!name.trim()) {
      setError("Назва не може бути порожньою");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const result = await onUpdateShopName(name.trim());
      // Sync input with server-confirmed value
      setName(result.shop_name);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося зберегти назву"));
    } finally {
      setSaving(false);
    }
  }

  async function handleLogoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await onUploadShopLogo(file);
    } catch (err) {
      setError(errorMessage(err, "Не вдалося завантажити лого"));
    } finally {
      setUploading(false);
      // Reset so same file can be re-selected after error
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDeleteLogo() {
    setError(null);
    try {
      await onDeleteShopLogo();
    } catch (err) {
      setError(errorMessage(err, "Не вдалося прибрати лого"));
    }
  }

  return (
    <div className="glass-card rounded-[20px] p-4 shadow-[var(--shadow-card)]">
      <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide mb-4">
        Профіль магазину
      </h3>

      {/* Logo */}
      <div className="flex items-center gap-4 mb-4">
        <div className="shrink-0 w-16 h-16 rounded-full overflow-hidden bg-[var(--glass-bg)] border border-[var(--line)] flex items-center justify-center">
          {shop.logo_url ? (
            <img src={shop.logo_url} alt="Лого магазину" className="w-full h-full object-cover" />
          ) : (
            <span className="text-2xl font-bold text-green-deep select-none">
              {shop.shop_name.charAt(0).toUpperCase()}
            </span>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="rounded-xl px-3 py-1.5 text-xs font-semibold text-green-deep border border-[var(--green)] disabled:opacity-50"
          >
            {uploading ? "Завантаження…" : "Завантажити лого"}
          </button>
          {shop.logo_url ? (
            <button
              type="button"
              onClick={() => void handleDeleteLogo()}
              className="rounded-xl px-3 py-1.5 text-xs font-semibold text-text-soft border border-[var(--line)]"
            >
              Прибрати
            </button>
          ) : null}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => void handleLogoChange(e)}
        />
      </div>

      {/* Name */}
      <label className="block mb-1 text-xs font-semibold text-text-soft">Назва магазину</label>
      <div className="flex gap-2">
        <input
          type="text"
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          className="flex-1 rounded-xl px-3 py-2 text-sm bg-[var(--glass-bg)] border border-[var(--line)] text-text outline-none focus:border-[var(--green)]"
        />
        <button
          type="button"
          disabled={saving || name.trim() === shop.shop_name}
          onClick={() => void handleSaveName()}
          className="shrink-0 rounded-xl px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          style={{
            background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
            boxShadow: "var(--shadow-cta)",
          }}
        >
          {saving ? "…" : "Зберегти"}
        </button>
      </div>

      {error ? (
        <p className="mt-2 text-xs text-[#b0460e]">{error}</p>
      ) : null}
    </div>
  );
}

export function SettingsScreen({
  shop,
  onOpenPaywall,
  onUpdateShopName,
  onUploadShopLogo,
  onDeleteShopLogo,
  scrollContainerRef,
}: SettingsScreenProps) {
  const statusInfo = shop?.status ? STATUS_LABELS[shop.status] : null;
  const planLabel = shop ? currentPlanLabel(shop) : "…";
  const chipLabel =
    planLabel === "Безкоштовний" ? "Free" : planLabel === "Пробний період" ? "Пробний" : "Активний";

  return (
    <div className="flex flex-col gap-4 pb-4">
      <h2 className="section-title">Налаштування</h2>

      <div className="glass-card rounded-[20px] p-4 shadow-[var(--shadow-card)]">
        <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide mb-3">
          Підписка
        </h3>

        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <p className="text-xs text-text-soft mb-0.5">Зараз активний</p>
            <p className="text-base font-bold text-text">{planLabel}</p>
            {shop?.max_products != null ? (
              <p className="text-xs text-text-soft mt-0.5">
                Ліміт: {shop.max_products} активних товарів
              </p>
            ) : null}
          </div>
          {shop ? (
            <span className="shrink-0 mt-0.5 rounded-full bg-[var(--state-ok)] px-2.5 py-0.5 text-[10px] font-bold text-green-deep">
              {chipLabel}
            </span>
          ) : null}
        </div>

        {statusInfo ? (
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-text-soft">Статус</span>
            <span className={`text-sm font-semibold ${statusInfo.colorClass}`}>
              {statusInfo.label}
            </span>
          </div>
        ) : null}

        {shop?.current_period_end ? (
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-text-soft">До</span>
            <span className="text-sm font-semibold text-text">
              {new Date(shop.current_period_end).toLocaleDateString("uk-UA")}
            </span>
          </div>
        ) : null}

        {shop?.role === "owner" ? (
          <button
            type="button"
            onClick={onOpenPaywall}
            className="mt-2 w-full rounded-2xl py-2.5 text-sm font-bold text-white"
            style={{
              background: "linear-gradient(135deg, var(--green) 0%, var(--green-deep) 100%)",
              boxShadow: "var(--shadow-cta)",
            }}
          >
            Змінити тариф
          </button>
        ) : null}
      </div>

      {shop?.role === "owner" ? (
        <ShopProfileSection
          shop={shop}
          onUpdateShopName={onUpdateShopName}
          onUploadShopLogo={onUploadShopLogo}
          onDeleteShopLogo={onDeleteShopLogo}
        />
      ) : null}

      {shop?.role === "owner" ? (
        <TeamSection scrollContainerRef={scrollContainerRef} />
      ) : null}

      {shop?.role === "owner" ? <NpKeySection /> : null}

      <div className="glass-card rounded-[20px] overflow-hidden shadow-[var(--shadow-card)]">
        <h3 className="text-sm font-bold text-text-soft uppercase tracking-wide px-4 pt-4 mb-1">
          Незабаром
        </h3>
        {COMING_SOON.map((label, i) => (
          <div
            key={label}
            className={`flex items-center justify-between px-4 py-3 ${
              i < COMING_SOON.length - 1 ? "border-b border-[var(--line)]" : "pb-4"
            }`}
          >
            <span className="text-sm text-text-soft">{label}</span>
            <span className="rounded-full bg-pastel-mint px-2 py-0.5 text-[10px] font-bold text-green-deep">
              Скоро
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
