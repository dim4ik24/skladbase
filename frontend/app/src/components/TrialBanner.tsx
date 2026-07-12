import { useTranslation } from "react-i18next";
import { trialDaysLeft } from "../lib/planStatus";
import type { Shop } from "../types";

interface TrialBannerProps {
  shop: Shop;
}

export function TrialBanner({ shop }: TrialBannerProps) {
  const { t } = useTranslation();
  const days = trialDaysLeft(shop);
  return <p className="banner banner-trial">{t("dashboard.trialBanner", { count: days })}</p>;
}
