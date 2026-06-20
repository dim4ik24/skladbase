/**
 * Атмосферний фон апки: завжди показує статичний CSS-фолбек («аврора» —
 * розмиті пастельні плями на --ink) миттєво, а WebGL-Beams підвантажує
 * лінькво (окремий чанк) і монтує лише якщо: не prefers-reduced-motion,
 * пристрій не «слабкий» (грубо — hardwareConcurrency), і WebGL не впав
 * (ErrorBoundary). Рендер паузиться через document.visibilitychange —
 * покриває й згортання Telegram WebApp у фон.
 */
import { Component, lazy, Suspense, useEffect, useState } from "react";
import type { ReactNode } from "react";

const LazyBeams = lazy(() => import("./Beams"));

const INK = "#0a0b0f";
const GREEN = "#def1d0";
const PINK = "#f8e5e5";
const BLUE = "#cdebf1";

class BeamsErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

function AuroraFallback() {
  return (
    <div className="atmosphere-fallback">
      <div
        className="aurora-blob"
        style={{ background: GREEN, width: 360, height: 360, top: "-12%", left: "-10%" }}
      />
      <div
        className="aurora-blob"
        style={{ background: BLUE, width: 320, height: 320, top: "28%", right: "-12%" }}
      />
      <div
        className="aurora-blob"
        style={{ background: PINK, width: 280, height: 280, bottom: "-14%", left: "22%" }}
      />
    </div>
  );
}

function prefersReducedMotion(): boolean {
  if (typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isWeakDevice(): boolean {
  const cores = navigator.hardwareConcurrency;
  return typeof cores === "number" && cores <= 4;
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

interface AtmosphereBackgroundProps {
  /** Призупиняє важкий WebGL-фон (Beams), коли на екрані вже є інший
   * важкий ефект (напр. Sparkles на екрані підписки) — один важкий ефект
   * за раз. Статична аврора лишається завжди. */
  suspended?: boolean;
}

export function AtmosphereBackground({ suspended = false }: AtmosphereBackgroundProps) {
  const [active, setActive] = useState(() => !document.hidden);
  const [canRenderBeams] = useState(
    () => !prefersReducedMotion() && !isWeakDevice() && supportsWebGL(),
  );

  useEffect(() => {
    function handleVisibility() {
      setActive(!document.hidden);
    }
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  return (
    <div className="atmosphere-wrap">
      <AuroraFallback />
      {canRenderBeams && !suspended ? (
        <BeamsErrorBoundary>
          <Suspense fallback={null}>
            <div className="beams-canvas-layer">
              <LazyBeams backgroundColor={INK} lightColor={GREEN} active={active} />
            </div>
          </Suspense>
        </BeamsErrorBoundary>
      ) : null}
    </div>
  );
}
