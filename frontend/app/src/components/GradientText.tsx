import type { CSSProperties, ReactNode } from "react";

interface GradientTextProps {
  children: ReactNode;
  className?: string;
  colors?: string[];
  animationSpeed?: number;
}

const DEFAULT_COLORS = ["#34C759", "#2BA84A", "#FF6B9D", "#34C759"];

export function GradientText({
  children,
  className = "",
  colors = DEFAULT_COLORS,
  animationSpeed = 8,
}: GradientTextProps) {
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(to right, ${colors.join(", ")})`,
    backgroundSize: "300% 100%",
    animationDuration: `${animationSpeed}s`,
  };

  return (
    <span className={`gradient-text${className ? ` ${className}` : ""}`} style={style}>
      {children}
    </span>
  );
}
