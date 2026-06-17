import type { Shop } from "../types";

interface HeaderProps {
  shop: Shop | null;
}

export function Header({ shop }: HeaderProps) {
  if (!shop) {
    return null;
  }

  return (
    <header className="shop-header">
      {shop.logo_url ? (
        <img className="shop-logo" src={shop.logo_url} alt="" />
      ) : (
        <div className="shop-logo shop-logo-placeholder" aria-hidden="true">
          {shop.shop_name.charAt(0).toUpperCase()}
        </div>
      )}
      <h1 className="shop-name">{shop.shop_name}</h1>
    </header>
  );
}
