import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { FinanceChartPoint, FinancePeriod } from "../types";

interface RevenueChartProps {
  period: FinancePeriod;
  chart: FinanceChartPoint[];
  onOpenHistory?: (date?: string) => void;
}

interface ChartBar {
  key: string;
  label: string;
  value: number;
  units: number;
}

const DOUBLE_TAP_MS = 300;

function pad(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function monthKey(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

function dayLabel(key: string): string {
  const [, m, d] = key.split("-");
  return `${d}.${m}`;
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-");
  return `${m}.${y.slice(2)}`;
}

// Бекенд групує по днях (week/month) або місяцях (year/all) — тут лише
// добудовуємо порожні бакети нулями, самі дати вже прийшли у chart.
function buildBars(period: FinancePeriod, chart: FinanceChartPoint[]): ChartBar[] {
  const pointByKey = new Map(chart.map((point) => [point.date, point]));
  const now = new Date();

  if (period === "week" || period === "month") {
    const days = period === "week" ? 7 : 30;
    const bars: ChartBar[] = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = dayKey(d);
      const point = pointByKey.get(key);
      bars.push({
        key,
        label: dayLabel(key),
        value: Number(point?.revenue ?? 0),
        units: point?.units ?? 0,
      });
    }
    return bars;
  }

  const bars: ChartBar[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = monthKey(d);
    const point = pointByKey.get(key);
    bars.push({
      key,
      label: monthLabel(key),
      value: Number(point?.revenue ?? 0),
      units: point?.units ?? 0,
    });
  }
  return bars;
}

export function RevenueChart({ period, chart, onOpenHistory }: RevenueChartProps) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const lastTapRef = useRef<{ index: number; time: number } | null>(null);
  const bars = buildBars(period, chart);
  const max = Math.max(1, ...bars.map((bar) => bar.value));
  const active = activeIndex != null ? bars[activeIndex] : null;
  const isDaily = period === "week" || period === "month";

  function handleBarTap(i: number) {
    setActiveIndex(i);

    const now = Date.now();
    const last = lastTapRef.current;
    if (last && last.index === i && now - last.time < DOUBLE_TAP_MS) {
      lastTapRef.current = null;
      onOpenHistory?.(isDaily ? bars[i].key : undefined);
      return;
    }
    lastTapRef.current = { index: i, time: now };
  }

  return (
    <div className="revenue-chart">
      <div className="revenue-chart-bars" role="img" aria-label={t("finance.chart.ariaLabel")}>
        {bars.map((bar, i) => (
          <button
            key={bar.key}
            type="button"
            className="revenue-chart-bar"
            style={{ height: `${Math.max(2, (bar.value / max) * 100)}%` }}
            onMouseEnter={() => setActiveIndex(i)}
            onMouseLeave={() => setActiveIndex(null)}
            onFocus={() => setActiveIndex(i)}
            onBlur={() => setActiveIndex(null)}
            onTouchStart={() => setActiveIndex(i)}
            onClick={() => handleBarTap(i)}
            aria-label={t("finance.chart.barAriaLabel", {
              label: bar.label,
              value: bar.value.toLocaleString("uk-UA", { maximumFractionDigits: 0 }),
            })}
          />
        ))}
      </div>
      <div className="revenue-chart-tooltip" aria-live="polite">
        {active
          ? t("finance.chart.tooltip", {
              label: active.label,
              units: active.units,
              value: active.value.toLocaleString("uk-UA", { maximumFractionDigits: 0 }),
            })
          : ""}
      </div>
      <div className="revenue-chart-axis">
        <span>{bars[0]?.label}</span>
        <span>{bars[bars.length - 1]?.label}</span>
      </div>
    </div>
  );
}
