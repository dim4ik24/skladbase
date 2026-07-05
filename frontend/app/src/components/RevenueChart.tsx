import { useState } from "react";
import type { FinanceChartPoint, FinancePeriod } from "../types";

interface RevenueChartProps {
  period: FinancePeriod;
  chart: FinanceChartPoint[];
}

interface ChartBar {
  key: string;
  label: string;
  value: number;
}

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
  const revenueByKey = new Map(chart.map((point) => [point.date, Number(point.revenue)]));
  const now = new Date();

  if (period === "week" || period === "month") {
    const days = period === "week" ? 7 : 30;
    const bars: ChartBar[] = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = dayKey(d);
      bars.push({ key, label: dayLabel(key), value: revenueByKey.get(key) ?? 0 });
    }
    return bars;
  }

  const bars: ChartBar[] = [];
  for (let i = 11; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = monthKey(d);
    bars.push({ key, label: monthLabel(key), value: revenueByKey.get(key) ?? 0 });
  }
  return bars;
}

export function RevenueChart({ period, chart }: RevenueChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const bars = buildBars(period, chart);
  const max = Math.max(1, ...bars.map((bar) => bar.value));
  const active = activeIndex != null ? bars[activeIndex] : null;

  return (
    <div className="revenue-chart">
      <div className="revenue-chart-bars" role="img" aria-label="Графік доходу за період">
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
            aria-label={`${bar.label}: ${bar.value.toLocaleString("uk-UA", { maximumFractionDigits: 0 })} ₴`}
          />
        ))}
      </div>
      <div className="revenue-chart-tooltip" aria-live="polite">
        {active
          ? `${active.label} · ${active.value.toLocaleString("uk-UA", { maximumFractionDigits: 0 })} ₴`
          : ""}
      </div>
      <div className="revenue-chart-axis">
        <span>{bars[0]?.label}</span>
        <span>{bars[bars.length - 1]?.label}</span>
      </div>
    </div>
  );
}
