/**
 * Panel — єдиний скляний стиль панелі (--panel/--line, blur, заокруглення
 * ~18px, motion-поява при монтуванні). Використовується для модалок/
 * висувних панелей (ProductFormModal, SubscriptionPaywall, секція
 * резервів) — поки немає референсного "панель.txt", це єдине місце,
 * яке потім легко замінити на дизайн із нього.
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
      className={`rounded-[18px] border border-[var(--line)] bg-[var(--panel)] backdrop-blur-xl ${className ?? ""}`}
      {...rest}
    >
      {children}
    </Component>
  );
}
