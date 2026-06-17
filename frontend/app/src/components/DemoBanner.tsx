interface DemoBannerProps {
  canClear: boolean;
  clearing: boolean;
  onClear: () => void;
}

export function DemoBanner({ canClear, clearing, onClear }: DemoBannerProps) {
  return (
    <div className="banner banner-demo">
      <span>Це приклади — додайте свої товари, коли будете готові.</span>
      {canClear ? (
        <button type="button" onClick={onClear} disabled={clearing}>
          {clearing ? "Очищаємо..." : "Очистити приклади"}
        </button>
      ) : null}
    </div>
  );
}
