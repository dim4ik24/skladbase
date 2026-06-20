/** Крихітний clsx-хелпер — проєкт не тягне shadcn/clsx, лише це й треба. */
export type ClassValue = string | number | boolean | null | undefined;

export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(" ");
}
