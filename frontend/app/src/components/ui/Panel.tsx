/**
 * Panel — flat green-deep surface (editorial sport-poster, без скла/blur).
 * Використовується для модалок, секцій резервів, paywall — єдиний каркас.
 */
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
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 32, mass: 0.7 }}
      className={`rounded-[18px] bg-green-deep ${className ?? ""}`}
      {...rest}
    >
      {children}
    </Component>
  );
}
