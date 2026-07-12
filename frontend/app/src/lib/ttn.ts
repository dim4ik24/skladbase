// Формат ТТН Нової Пошти: 14 цифр, номер починається з "20" (звичайні
// відправлення) або "59" (внутрішні/особливі типи). Порожній рядок — валідний
// (ТТН опційний), тож перевіряти лише непорожній ввід.
// Текст помилки формату — ключ i18n `shipping.ttnError` (uk.json), не тут:
// викликається з ReservationSheet/ShipSheet, де є доступ до useTranslation.
const TTN_REGEX = /^(20|59)\d{12}$/;

export function isValidTtn(ttn: string): boolean {
  return TTN_REGEX.test(ttn);
}
