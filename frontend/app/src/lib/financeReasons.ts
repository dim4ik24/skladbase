// i18n-ключі причин для фінансового дашборда (домен reasons.* у uk.json).
// Ключі мають збігатися з RELEASE_REASONS / NOT_PICKED_UP_REASONS у
// app/services/inventory.py (див. також ReleaseSheet.tsx / NotPickedUpSheet.tsx).
// reasonLabel() повертає ключ (або сирий reason, якщо мапа його не знає) —
// виклик t() лишається на боці компонента, бо тут немає доступу до хука.
export const RELEASE_REASON_LABELS: Record<string, string> = {
  customer_changed_mind: "reasons.customerChangedMind",
  unresponsive: "reasons.unresponsive",
  mistaken_reservation: "reasons.mistakenReservation",
  other: "reasons.other",
};

export const RETURN_REASON_LABELS: Record<string, string> = {
  did_not_pick_up: "reasons.didNotPickUp",
  refused: "reasons.refused",
  other: "reasons.other",
};

export function reasonLabel(map: Record<string, string>, reason: string): string {
  return map[reason] ?? reason;
}
