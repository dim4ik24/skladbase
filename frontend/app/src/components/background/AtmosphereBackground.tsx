/**
 * AtmosphereBackground — full-screen Iridescence (ogl) shader background.
 *
 * Guards (render static gradient instead of WebGL):
 *   - prefers-reduced-motion
 *   - WebGL unavailable / runtime error  (ErrorBoundary catches it)
 *
 * `suspended` prop kept for API compat with App.tsx caller.
 */
import { Component, lazy, Suspense, type ReactNode, type CSSProperties } from "react";

const IridescenceCanvas = lazy(() =>
  import("./Iridescence").then((m) => ({ default: m.IridescenceCanvas })),
);

interface AtmosphereBackgroundProps {
  suspended?: boolean;
}

const WRAPPER: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 0,
  pointerEvents: "none",
  opacity: 0.42,
};

// Pink-green fintech fallback (two radial blobs on light base).
const FALLBACK_STYLE: CSSProperties = {
  width: "100%",
  height: "100%",
  background: [
    "radial-gradient(ellipse 70% 50% at 25% 35%, #FFD0E8 0%, transparent 65%)",
    "radial-gradient(ellipse 60% 45% at 75% 65%, #C8F0D8 0%, transparent 65%)",
    "#F4F6F5",
  ].join(", "),
};

function StaticFallback() {
  return <div style={FALLBACK_STYLE} />;
}

// Catches WebGL errors thrown by IridescenceCanvas (synchronous throw) or R3F.
class WebGLErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError(error: unknown) {
    console.error("[AtmosphereBackground] WebGL error caught by boundary:", error);
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

  if (prefersReduced) {
    return (
      <div style={WRAPPER} aria-hidden="true">
        <StaticFallback />
      </div>
    );
  }

  return (
    <div style={WRAPPER} aria-hidden="true">
      <WebGLErrorBoundary>
        <Suspense fallback={<StaticFallback />}>
          <IridescenceCanvas
            color={[1.0, 0.85, 0.90]}
            speed={0.9}
            amplitude={0.1}
            mouseReact={false}
          />
        </Suspense>
      </WebGLErrorBoundary>
    </div>
  );
}
