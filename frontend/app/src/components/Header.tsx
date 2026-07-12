import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GradientText } from "./GradientText";
import type { Shop, ShopSummary } from "../types";

interface HeaderProps {
  shop: Shop | null;
  shops?: ShopSummary[];
  onSwitchShop?: (shopId: number) => void;
}

export function Header({ shop, shops = [], onSwitchShop }: HeaderProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  if (!shop) {
    return null;
  }

  const canSwitch = shops.length > 1;
  const nameHeading = (
    <h1 className="shop-name">
      <GradientText>{shop.shop_name}</GradientText>
    </h1>
  );

  return (
    <header className="shop-header">
      {shop.logo_url ? (
        <img className="shop-logo" src={shop.logo_url} alt="" />
      ) : (
        <div className="shop-logo shop-logo-placeholder" aria-hidden="true">
          {shop.shop_name.charAt(0).toUpperCase()}
        </div>
      )}

      <div className="shop-name-wrap">
        {canSwitch ? (
          <button
            type="button"
            className="shop-name-button"
            aria-haspopup="listbox"
            aria-expanded={open}
            onClick={() => setOpen((prev) => !prev)}
          >
            {nameHeading}
            <ChevronDown size={18} className="shop-switcher-chevron" aria-hidden="true" />
          </button>
        ) : (
          nameHeading
        )}

        {open ? (
          <>
            <div
              className="shop-switcher-backdrop"
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />
            <ul className="shop-switcher-list" role="listbox">
              {shops.map((s) => (
                <li key={s.shop_id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={s.shop_id === shop.shop_id}
                    className="shop-switcher-item"
                    onClick={() => {
                      onSwitchShop?.(s.shop_id);
                      setOpen(false);
                    }}
                  >
                    <span className="shop-switcher-avatar" aria-hidden="true">
                      {s.logo_url ? (
                        <img src={s.logo_url} alt="" />
                      ) : (
                        s.shop_name.charAt(0).toUpperCase()
                      )}
                    </span>
                    <span className="shop-switcher-info">
                      <span className="shop-switcher-name">{s.shop_name}</span>
                      <span className="shop-switcher-role">
                        {s.role === "owner" ? t("common.roleOwner") : t("common.roleManager")}
                      </span>
                    </span>
                    {s.shop_id === shop.shop_id ? (
                      <Check size={16} className="shop-switcher-check" aria-hidden="true" />
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </header>
  );
}
