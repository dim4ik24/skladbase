import { trialDaysLeft } from "../lib/planStatus";
import type { Shop } from "../types";

interface TrialBannerProps {
  shop: Shop;
}

export function TrialBanner({ shop }: TrialBannerProps) {
  const days = trialDaysLeft(shop);
  return <p className="banner banner-trial">Тріал: залишилось {days} днів</p>;
}
