import { useTranslation } from "react-i18next";

interface DemoBannerProps {
  canClear: boolean;
  clearing: boolean;
  onClear: () => void;
}

export function DemoBanner({ canClear, clearing, onClear }: DemoBannerProps) {
  const { t } = useTranslation();
  return (
    <div className="banner banner-demo">
      <span>{t("dashboard.demoText")}</span>
      {canClear ? (
        <button type="button" onClick={onClear} disabled={clearing}>
          {clearing ? t("dashboard.demoClearing") : t("dashboard.demoClear")}
        </button>
      ) : null}
    </div>
  );
}
