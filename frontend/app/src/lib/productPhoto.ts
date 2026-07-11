import type { Product } from "../types";

export interface ResolvedProductPhoto {
  photoUrl: string | null;
  letter: string;
}

/** Перше фото товару (за position) або чип-літера з назви — спільний резолв
 * для рядків "Топ товарів" (Дашборд) та історії (HistorySheet). */
export function resolveProductPhoto(
  product: Product | undefined,
  fallbackName: string,
): ResolvedProductPhoto {
  const sortedPhotos = product ? [...product.photos].sort((a, b) => a.position - b.position) : [];
  const photoUrl = sortedPhotos[0]?.url ?? null;
  const letter = (product?.name ?? fallbackName).charAt(0).toUpperCase();
  return { photoUrl, letter };
}
