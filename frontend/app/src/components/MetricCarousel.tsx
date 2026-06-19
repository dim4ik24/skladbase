/**
 * MetricCarousel — дашборд-метрики магазину зверху каталогу. Адаптовано
 * з пасти MinimalCarousel (motion/react, layoutId-перехід картка<->грід):
 * прибрано домен криптокошельків (Copy Address/Edit), залишено
 * expand/collapse-взаємодію. Дані — лише з уже завантажених
 * products/reservations (App.tsx), нових запитів немає.
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
              transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
              className={`relative flex h-36 w-full cursor-pointer flex-col justify-between rounded-[26px] p-5 shadow-lg ${activeCard.bgClass} ${activeCard.textClass}`}
            >
              <activeCard.icon size={32} strokeWidth={1.75} />
              <div>
                <h3 className="text-base font-medium opacity-80">{activeCard.title}</h3>
                <p className="font-mono-price text-3xl font-bold">{activeCard.value}</p>
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
              transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
              className={`flex cursor-pointer flex-col justify-between rounded-[18px] p-3 shadow-md ${card.bgClass} ${card.textClass} ${activeId ? "h-20" : "h-24"}`}
            >
              <card.icon size={activeId ? 16 : 20} strokeWidth={1.75} />
              <div>
                <p
                  className={`truncate font-medium opacity-80 ${activeId ? "text-[10px]" : "text-xs"}`}
                >
                  {card.title}
                </p>
                <p className={`font-mono-price font-bold ${activeId ? "text-sm" : "text-lg"}`}>
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
