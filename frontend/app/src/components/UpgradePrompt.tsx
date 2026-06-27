interface UpgradePromptProps {
  message: string;
  onOpenPaywall: () => void;
  onClose: () => void;
}

export function UpgradePrompt({ message, onOpenPaywall, onClose }: UpgradePromptProps) {
  return (
    <div className="upgrade-prompt" role="status">
      <p className="upgrade-prompt__message">{message}</p>
      <div className="upgrade-prompt__actions">
        <button type="button" className="upgrade-prompt__cta" onClick={onOpenPaywall}>
          Обрати тариф
        </button>
        <button type="button" className="upgrade-prompt__close" onClick={onClose}>
          Закрити
        </button>
      </div>
    </div>
  );
}
