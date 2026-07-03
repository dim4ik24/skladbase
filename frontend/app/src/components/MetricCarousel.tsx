import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";
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
  // null (не cards[0]) — навмисна відмінність від старої версії: старий
  // код тримав перший card featured одразу з монтування, що з новим
  // "2-й тап по вже збільшеній -> навігація" означало б, що перший-ліпший
  // тап на дефолтно-збільшену картку одразу кидає на Склад без свідомого
  // 1-го тапу. Починаємо з "нічого не вибрано" — 4 рівні картки.
  const [activeId, setActiveId] = useState<string | null>(null);
  const prefersReducedMotion = useReducedMotion();
  const activeCard = cards.find((card) => card.id === activeId) ?? null;
  const secondaryCards = cards.filter((card) => card.id !== activeId);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const springTransition = prefersReducedMotion
    ? { duration: 0 }
    : { type: "spring" as const, bounce: 0.15, duration: 0.5 };

  function handleTap(id: string) {
    if (id === activeId) {
      onNavigate?.();
      return;
    }
    setActiveId(id);
  }

  // Тап на активну картку тепер навігує (не знімає виділення), тож без
  // цього не було б способу повернутись до "усі 4 рівні" інакше, ніж
  // вибравши іншу картку або перейшовши геть.
  useEffect(() => {
    if (activeId === null) return;
    function handlePointerDown(e: PointerEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setActiveId(null);
      }
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [activeId]);

  return (
    <div ref={wrapperRef} className="w-full select-none mb-4">
      <motion.div layout className="flex flex-col gap-2">
        <AnimatePresence mode="popLayout">
          {activeCard ? (
            <motion.div
              key={activeCard.id}
              layoutId={activeCard.id}
              role="button"
              aria-label={activeCard.title}
              aria-pressed="true"
              onClick={() => handleTap(activeCard.id)}
              transition={springTransition}
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
                  <MetricValue value={activeCard.value} />
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
              role="button"
              aria-label={card.title}
              aria-pressed="false"
              onClick={() => handleTap(card.id)}
              transition={springTransition}
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
                  <MetricValue value={card.value} />
                </p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>
    </div>
  );
}
