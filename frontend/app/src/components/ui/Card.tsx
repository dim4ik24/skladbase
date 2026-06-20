/**
 * Card/CardHeader/CardContent — локальна міні-заміна shadcn Card (нема
 * shadcn-проєкту/CSS-змінних --card/--card-foreground). Стилізовано під
 * нашу палітру (--panel/--line), без власної motion-анімації — реveal
 * картки на рівні обгортки (Reveal), не тут.
 */
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-[var(--line)] bg-[var(--panel)] backdrop-blur-xl",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5 p-6", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}
