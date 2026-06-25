import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { LucideIcon } from "lucide-react";

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
}

export function MetricCarousel({ cards }: MetricCarouselProps) {
  const [activeId, setActiveId] = useState<string | null>(cards[0]?.id ?? null);
  const activeCard = cards.find((card) => card.id === activeId) ?? null;
  const secondaryCards = cards.filter((card) => card.id !== activeId);

  return (
    <div className="w-full select-none mb-4">
      <motion.div layout className="flex flex-col gap-2">
        <AnimatePresence mode="popLayout">
          {activeCard ? (
            <motion.div
              key={activeCard.id}
              layoutId={activeCard.id}
              onClick={() => setActiveId(null)}
              transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
              className="relative flex h-36 w-full cursor-pointer flex-col justify-between rounded-[20px] bg-surface p-5 shadow-[var(--shadow-card)]"
            >
              <div className={`flex h-10 w-10 items-center justify-center rounded-full ${activeCard.iconBg}`}>
                <activeCard.icon size={20} strokeWidth={1.8} className={activeCard.iconColor} aria-hidden="true" />
              </div>
              <div>
                <p className="mb-0.5 text-[11px] font-semibold uppercase tracking-widest text-text-soft">
                  {activeCard.title}
                </p>
                <p className="font-sans text-5xl font-bold leading-none tracking-tight text-text">
                  {activeCard.value}
                </p>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <motion.div layout className={`grid gap-2 ${activeId ? "grid-cols-3" : "grid-cols-4"}`}>
          {(activeId ? secondaryCards : cards).map((card) => (
            <motion.div
              key={card.id}
              layoutId={card.id}
              onClick={() => setActiveId(card.id)}
              transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
              className={`flex cursor-pointer flex-col justify-between rounded-[16px] bg-surface p-3 shadow-[var(--shadow-card)] ${activeId ? "h-20" : "h-24"}`}
            >
              <div className={`flex h-7 w-7 items-center justify-center rounded-full ${card.iconBg}`}>
                <card.icon size={activeId ? 12 : 14} strokeWidth={1.8} className={card.iconColor} aria-hidden="true" />
              </div>
              <div>
                <p className={`truncate font-semibold uppercase tracking-widest text-text-soft ${activeId ? "text-[9px]" : "text-[10px]"}`}>
                  {card.title}
                </p>
                <p className={`font-bold leading-none tracking-tight text-text ${activeId ? "text-xl" : "text-3xl"}`}>
                  {card.value}
                </p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>
    </div>
  );
}
