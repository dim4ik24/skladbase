import type { RefObject } from "react";
import { ScrollFloat } from "./ScrollFloat";
import type { Shop } from "../types";

interface HeaderProps {
  shop: Shop | null;
  scrollContainerRef?: RefObject<HTMLElement | null>;
}

export function Header({ shop, scrollContainerRef }: HeaderProps) {
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
      <ScrollFloat as="h1" className="shop-name" scrollContainerRef={scrollContainerRef}>
        {shop.shop_name}
      </ScrollFloat>
    </header>
  );
}
