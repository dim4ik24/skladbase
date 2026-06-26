/**
 * Iridescence — ogl-based fullscreen shader background.
 * Ported from Iridescence-original.jsx. Adapted for Vite+TS, light fintech palette.
 *
 * Color tuning vs. original [1,1,1]:
 *   uColor [1.0, 0.85, 0.90] — boosts pink (R), keeps green present (G 0.85),
 *   suppresses blue/violet (B 0.90). Results in a rose-to-green iridescent sweep
 *   on the white clearColor base.
 *
 * mouseReact defaults to false (no pointer on mobile Telegram).
 * IridescenceCanvas throws synchronously if WebGL is unavailable so that
 * WebGLErrorBoundary in AtmosphereBackground can catch it.
 */
import { useEffect, useRef, type CSSProperties } from "react";
import { Renderer, Program, Mesh, Color, Triangle } from "ogl";

// ── Shaders (exact from original) ─────────────────────────────────────────────
const VERTEX = `
attribute vec2 uv;
attribute vec2 position;
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}
`;

const FRAGMENT = `
precision highp float;
uniform float uTime;
uniform vec3 uColor;
uniform vec3 uResolution;
uniform vec2 uMouse;
uniform float uAmplitude;
uniform float uSpeed;
varying vec2 vUv;
void main() {
  float mr = min(uResolution.x, uResolution.y);
  vec2 uv = (vUv.xy * 2.0 - 1.0) * uResolution.xy / mr;
  uv += (uMouse - vec2(0.5)) * uAmplitude;
  float d = -uTime * 0.5 * uSpeed;
  float a = 0.0;
  for (float i = 0.0; i < 8.0; ++i) {
    a += cos(i - d - a * uv.x);
    d += sin(uv.y * i + a);
  }
  d += uTime * 0.5 * uSpeed;
  vec3 col = vec3(cos(uv * vec2(d, a)) * 0.6 + 0.4, cos(a + d) * 0.5 + 0.5);
  col = cos(col * cos(vec3(d, a, 2.5)) * 0.5 + 0.5) * uColor;
  gl_FragColor = vec4(col, 1.0);
}
`;

// ── Props ──────────────────────────────────────────────────────────────────────
export interface IridescenceProps {
  color?: [number, number, number];
  speed?: number;
  amplitude?: number;
  mouseReact?: boolean;
}

const FILL: CSSProperties = { width: "100%", height: "100%" };

// ── Inner component (mounts ogl canvas) ───────────────────────────────────────
function IridescenceInner({
  color = [1.0, 0.85, 0.90],
  speed = 0.9,
  amplitude = 0.1,
  mouseReact = false,
}: IridescenceProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mousePos = useRef<[number, number]>([0.5, 0.5]);

  useEffect(() => {
    const ctn = containerRef.current;
    if (!ctn) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let renderer: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let program: any;
    let animId = 0;

    try {
      renderer = new Renderer({ alpha: false, antialias: false });
    } catch (err) {
      console.error("[Iridescence] Renderer init failed:", err);
      return;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const gl: any = renderer.gl;
    gl.clearColor(1, 1, 1, 1);

    const mouseArr = new Float32Array([mousePos.current[0], mousePos.current[1]]);

    function resize() {
      if (!ctn) return; // ctn is const & non-null here; guard satisfies TS closures
      renderer.setSize(ctn.offsetWidth, ctn.offsetHeight);
      if (program) {
        program.uniforms.uResolution.value = new Color(
          gl.canvas.width,
          gl.canvas.height,
          gl.canvas.width / gl.canvas.height,
        );
      }
    }

    window.addEventListener("resize", resize, false);
    resize();

    try {
      const geometry = new Triangle(gl);
      program = new Program(gl, {
        vertex: VERTEX,
        fragment: FRAGMENT,
        uniforms: {
          uTime: { value: 0 },
          uColor: { value: new Color(...color) },
          uResolution: {
            value: new Color(
              gl.canvas.width,
              gl.canvas.height,
              gl.canvas.width / gl.canvas.height,
            ),
          },
          uMouse: { value: mouseArr },
          uAmplitude: { value: amplitude },
          uSpeed: { value: speed },
        },
      });

      const mesh = new Mesh(gl, { geometry, program });
      ctn.appendChild(gl.canvas);
      console.log("[Iridescence] WebGL shader mounted successfully");

      function update(t: number) {
        animId = requestAnimationFrame(update);
        program.uniforms.uTime.value = t * 0.001;
        renderer.render({ scene: mesh });
      }
      animId = requestAnimationFrame(update);
    } catch (err) {
      console.error("[Iridescence] Shader/Program init failed:", err);
      window.removeEventListener("resize", resize);
      return;
    }

    function handleMouseMove(e: MouseEvent) {
      if (!ctn) return;
      const rect = ctn.getBoundingClientRect();
      mouseArr[0] = (e.clientX - rect.left) / rect.width;
      mouseArr[1] = 1.0 - (e.clientY - rect.top) / rect.height;
    }

    if (mouseReact) ctn.addEventListener("mousemove", handleMouseMove);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      if (mouseReact) ctn.removeEventListener("mousemove", handleMouseMove);
      if (ctn && gl.canvas.parentNode === ctn) ctn.removeChild(gl.canvas);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, [color, speed, amplitude, mouseReact]);

  return <div ref={containerRef} style={FILL} />;
}

// ── IridescenceCanvas (lazy-loaded entry point) ────────────────────────────────
// Throws synchronously when WebGL is unavailable so WebGLErrorBoundary catches it.
export function IridescenceCanvas(props: IridescenceProps) {
  const test = document.createElement("canvas");
  const ctx = test.getContext("webgl") ?? test.getContext("experimental-webgl");
  if (!ctx) {
    const err = new Error("WebGL not supported");
    console.error("[Iridescence] WebGL unavailable:", err);
    throw err;
  }
  return <IridescenceInner {...props} />;
}
