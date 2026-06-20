/**
 * Reveal — заміна відсутнього TimelineContent (немає референсного
 * вихідника). Простий reveal на motion/react: fade + blur + translate за
 * індексом, спрацьовує при монтуванні (без scroll-tracking — TimelineContent
 * прив'язував анімацію до timelineRef/в'юпорту, тут такого немає і не
 * потрібно — секція підписки невелика, завжди у в'юпорті при показі).
 */
import type { ReactNode } from "react";
import { motion } from "motion/react";

const revealVariants = {
  hidden: { opacity: 0, y: -20, filter: "blur(10px)" },
  visible: (index: number) => ({
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { delay: index * 0.12, duration: 0.5 },
  }),
};

interface RevealProps {
  index: number;
  as?: "div" | "p";
  className?: string;
  children: ReactNode;
}

export function Reveal({ index, as = "div", className, children }: RevealProps) {
  const Component = as === "p" ? motion.p : motion.div;
  return (
    <Component
      custom={index}
      initial="hidden"
      animate="visible"
      variants={revealVariants}
      className={className}
    >
      {children}
    </Component>
  );
}
