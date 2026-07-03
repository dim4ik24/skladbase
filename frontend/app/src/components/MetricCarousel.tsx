import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { LucideIcon } from "lucide-react";
import { useCountUp } from "../hooks/useCountUp";

export interface MetricCardData {
  id: string;
  title: string;
  value: number;
  iconBg: string;    // Tailwind class: pastel bg for the icon circle
  iconColor: string; // Tailwind class: icon stroke color
  icon: LucideIcon;
}

interface MetricCarouselProps {
  cards: MetricCardData[];
  onNavigate?: () => void;
}

function MetricValue({ value }: { value: number }) {
  const display = useCountUp(value);
  return <>{display}</>;
}

export function MetricCarousel({ cards, onNavigate }: MetricCarouselProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    if (selectedId === null) return;
    function handlePointerDown(e: PointerEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setSelectedId(null);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [selectedId]);

  function handleCardClick(id: string) {
    if (id === selectedId) {
      onNavigate?.();
      return;
    }
    setSelectedId(id);
  }

  return (
    <div ref={wrapperRef} className="w-full select-none mb-4 grid grid-cols-4 gap-2">
      {cards.map((card, index) => {
        const isSelected = card.id === selectedId;
        return (
          <motion.div
            key={card.id}
            role="button"
            aria-label={card.title}
            aria-pressed={isSelected}
            onClick={() => handleCardClick(card.id)}
            initial={prefersReducedMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={
              prefersReducedMotion
                ? { duration: 0 }
                : { duration: 0.3, delay: Math.min(index, 9) * 0.04 }
            }
            className={`metric-card flex h-24 cursor-pointer flex-col justify-between rounded-[16px] bg-surface p-3 shadow-[var(--shadow-card)]${
              isSelected ? " metric-card--selected" : ""
            }`}
          >
            <motion.div
              className={`flex h-7 w-7 items-center justify-center rounded-full ${card.iconBg}`}
              animate={{ scale: isSelected && !prefersReducedMotion ? 1.15 : 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 12 }}
            >
              <card.icon size={14} strokeWidth={1.8} className={card.iconColor} aria-hidden="true" />
            </motion.div>
            <div>
              <p className="truncate text-[10px] font-semibold uppercase tracking-widest text-text-soft">
                {card.title}
              </p>
              <p className="text-3xl font-bold leading-none tracking-tight text-text">
                <MetricValue value={card.value} />
              </p>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
