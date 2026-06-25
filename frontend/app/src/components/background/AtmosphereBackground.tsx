/**
 * AuroraBackground — WebGL Beams background, loaded lazily.
 *
 * Guards (render static CSS gradient instead of WebGL):
 *   - prefers-reduced-motion
 *   - hardwareConcurrency ≤ 4 (low-end device)
 *   - WebGL error in child (ErrorBoundary catches, no white screen)
 *
 * `suspended` prop kept for API compat with App.tsx caller.
 */
import { Component, lazy, Suspense, type ReactNode, type CSSProperties } from "react";

const BeamsCanvas = lazy(() =>
  import("./Beams").then((m) => ({ default: m.BeamsCanvas })),
);

interface AtmosphereBackgroundProps {
  suspended?: boolean;
}

const WRAPPER: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 0,
  pointerEvents: "none",
  opacity: 0.45,
};

const FALLBACK_STYLE: CSSProperties = {
  width: "100%",
  height: "100%",
  background:
    "radial-gradient(110% 60% at 50% -5%, #FFD0E8 0%, transparent 65%), #F4F6F5",
};

function StaticFallback() {
  return <div style={FALLBACK_STYLE} />;
}

// Catches WebGL context errors thrown by R3F Canvas
class WebGLErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  render() {
    return this.state.hasError ? <StaticFallback /> : this.props.children;
  }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function AtmosphereBackground(_props: AtmosphereBackgroundProps) {
  const prefersReduced =
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isLowEnd = (navigator.hardwareConcurrency ?? 8) <= 4;

  if (prefersReduced || isLowEnd) {
    return (
      <div style={WRAPPER} aria-hidden="true">
        <StaticFallback />
      </div>
    );
  }

  return (
    <>
      <div style={WRAPPER} aria-hidden="true">
        <WebGLErrorBoundary>
          <Suspense fallback={<StaticFallback />}>
            <BeamsCanvas
              beamWidth={3}
              beamNumber={8}
              lightColor="#FFAFCF"
              speed={1.5}
              noiseIntensity={0.8}
              rotation={30}
            />
          </Suspense>
        </WebGLErrorBoundary>
      </div>
    </>
  );
}
