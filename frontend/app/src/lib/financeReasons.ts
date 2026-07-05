// Людські назви причин для фінансового дашборда. Значення мають збігатися
// з RELEASE_REASONS / NOT_PICKED_UP_REASONS у app/services/inventory.py
// (див. також ReleaseSheet.tsx / NotPickedUpSheet.tsx).
export const RELEASE_REASON_LABELS: Record<string, string> = {
  customer_changed_mind: "Клієнт передумав",
  unresponsive: "Не відповідає",
  mistaken_reservation: "Помилковий резерв",
  other: "Інше",
};

export const RETURN_REASON_LABELS: Record<string, string> = {
  did_not_pick_up: "Не забрав з пошти",
  refused: "Відмовився",
  other: "Інше",
};

export function reasonLabel(map: Record<string, string>, reason: string): string {
  return map[reason] ?? reason;
}
