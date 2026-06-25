import type { ComponentProps } from "react";
import { motion } from "motion/react";

interface PanelOwnProps {
  as?: "div" | "section";
}

type PanelProps = PanelOwnProps & Omit<ComponentProps<typeof motion.div>, "as">;

export function Panel({ as = "div", className, children, ...rest }: PanelProps) {
  const Component = as === "section" ? motion.section : motion.div;
  return (
    <Component
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 380, damping: 32, mass: 0.7 }}
      className={`rounded-[20px] bg-surface shadow-[var(--shadow-card)] ${className ?? ""}`}
      {...rest}
    >
      {children}
    </Component>
  );
}
