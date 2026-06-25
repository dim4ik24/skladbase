/**
 * AuroraBackground — CSS-only floating color blobs, no WebGL/three.js.
 * Animates with transform-only keyframes (compositor-friendly, no repaint).
 * On hardwareConcurrency ≤ 4: blobs render static (no animation).
 * On prefers-reduced-motion: global CSS rule kills all animations.
 * `suspended` prop kept for API compat with App.tsx caller.
 */

interface AtmosphereBackgroundProps {
  suspended?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function AtmosphereBackground(_props: AtmosphereBackgroundProps) {
  const isLowEnd = (navigator.hardwareConcurrency ?? 8) <= 4;

  return (
    <div
      className={`aurora-root${isLowEnd ? " aurora--static" : ""}`}
      aria-hidden="true"
    >
      <div className="aurora-blob aurora-blob--pink" />
      <div className="aurora-blob aurora-blob--mint" />
      <div className="aurora-blob aurora-blob--rose" />
      <div className="aurora-blob aurora-blob--lavender" />
    </div>
  );
}
