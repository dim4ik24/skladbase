import type { TemplateField } from "../types";

export const COLOR_MAP: Record<string, string> = {
  чорний: "#1C2520",
  білий: "#FFFFFF",
  рожевий: "#FF6B9D",
  червоний: "#FF3B30",
  синій: "#007AFF",
  зелений: "#34C759",
  сірий: "#8E8E93",
  жовтий: "#FFD60A",
  помаранчевий: "#FF9500",
  бежевий: "#C8B99A",
  коричневий: "#8B5E3C",
  фіолетовий: "#AF52DE",
};

const COLOR_AXIS_KEYS = new Set(["колір", "color", "colour"]);

export function resolveChipColor(
  axes: TemplateField[],
  axisValues: Record<string, string>,
): string | null {
  for (const axis of axes) {
    if (COLOR_AXIS_KEYS.has(axis.key.toLowerCase())) {
      const raw = axisValues[axis.key];
      if (raw) return COLOR_MAP[raw.toLowerCase().trim()] ?? null;
    }
  }
  return null;
}

export function chipLetter(
  axes: TemplateField[],
  axisValues: Record<string, string>,
): string {
  for (const axis of axes) {
    const v = axisValues[axis.key];
    if (v) return v.charAt(0).toUpperCase();
  }
  return "?";
}
