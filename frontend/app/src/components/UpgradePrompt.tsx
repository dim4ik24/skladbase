import { useTranslation } from "react-i18next";

interface UpgradePromptProps {
  message: string;
  onOpenPaywall: () => void;
  onClose: () => void;
}

export function UpgradePrompt({ message, onOpenPaywall, onClose }: UpgradePromptProps) {
  const { t } = useTranslation();
  return (
    <div className="upgrade-prompt" role="status">
      <p className="upgrade-prompt__message">{message}</p>
      <div className="upgrade-prompt__actions">
        <button type="button" className="upgrade-prompt__cta" onClick={onOpenPaywall}>
          {t("paywall.chooseButton")}
        </button>
        <button type="button" className="upgrade-prompt__close" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
    </div>
  );
}
