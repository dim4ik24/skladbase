/**
 * MetricCarousel — табло метрик магазину. Editorial sport-poster:
 * велетенські Unbounded-цифри на green-deep плоских блоках, expand-анімація
 * через motion layoutId. Без тіней/скла.
 */
import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { LucideIcon } from "lucide-react";

export interface MetricCardData {
  id: string;
  title: string;
  value: number;
  bgClass: string;
  textClass: string;
  icon: LucideIcon;
}

interface MetricCarouselProps {
  cards: MetricCardData[];
}

export function MetricCarousel({ cards }: MetricCarouselProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
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
              className={`relative flex h-40 w-full cursor-pointer flex-col justify-between rounded-2xl p-5 ${activeCard.bgClass} ${activeCard.textClass}`}
            >
              <activeCard.icon size={28} strokeWidth={1.5} />
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest opacity-60 mb-1">
                  {activeCard.title}
                </p>
                <p className="font-display text-6xl font-bold leading-none tracking-tight">
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
              className={`flex cursor-pointer flex-col justify-between rounded-2xl p-3 ${card.bgClass} ${card.textClass} ${activeId ? "h-20" : "h-24"}`}
            >
              <card.icon size={activeId ? 14 : 18} strokeWidth={1.5} />
              <div>
                <p
                  className={`truncate font-semibold uppercase tracking-widest opacity-60 ${activeId ? "text-[9px]" : "text-[10px]"}`}
                >
                  {card.title}
                </p>
                <p className={`font-display font-bold leading-none tracking-tight ${activeId ? "text-xl" : "text-3xl"}`}>
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
