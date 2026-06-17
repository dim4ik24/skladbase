interface TrialBannerProps {
  trialEndsAt: string;
}

export function TrialBanner({ trialEndsAt }: TrialBannerProps) {
  // Лічильник днів — за визначенням залежить від поточного часу (Date.now()),
  // тож не може бути «чистим» обчисленням; нешкідливо для цього UI.
  // eslint-disable-next-line react-hooks/purity
  const msLeft = new Date(trialEndsAt).getTime() - Date.now();
  const days = Math.max(0, Math.ceil(msLeft / (24 * 60 * 60 * 1000)));

  return <p className="banner banner-trial">Тріал: залишилось {days} днів</p>;
}
