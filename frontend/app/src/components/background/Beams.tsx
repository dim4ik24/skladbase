/**
 * Beams — full-screen WebGL animated light-ray background.
 * Light palette: soft pink rays on #F4F6F5 base.
 * Loaded lazily by AtmosphereBackground — NOT in the initial bundle.
 *
 * Perf notes:
 *   - ScreenQuad draws one full-screen triangle (zero vertex overhead)
 *   - Only uTime uniform changes per frame (no geometry updates)
 *   - frameloop="never" while document.hidden (visibility API)
 *   - dpr capped at [1, 1.5]; powerPreference:"low-power"
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { ScreenQuad } from "@react-three/drei";
import * as THREE from "three";

// ── Shaders ─────────────────────────────────────────────────────────────
// position.xy from ScreenQuad is already in clip space (−1..1).
// We bypass MVP transform and derive UV manually.
const VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = position.xy * 0.5 + 0.5;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const FRAG = /* glsl */ `
  precision highp float;

  uniform float uTime;
  uniform float uSpeed;
  uniform float uBeamWidth;
  uniform int   uBeamNumber;
  uniform vec3  uLightColor;
  uniform float uNoiseIntensity;
  uniform float uRotation;

  varying vec2 vUv;

  float hash(float n) {
    return fract(sin(n * 127.1) * 43758.5453);
  }

  void main() {
    vec2 uv = vUv;

    // Rotate UV around screen centre
    float cosR = cos(uRotation);
    float sinR = sin(uRotation);
    uv -= 0.5;
    uv  = vec2(cosR * uv.x - sinR * uv.y, sinR * uv.x + cosR * uv.y);
    uv += 0.5;

    float n = float(uBeamNumber);
    float t = uTime * uSpeed * 0.04;

    // Tile X into N beam cells
    float scaledX = uv.x * n;
    float beamIdx = floor(scaledX);
    float localX  = fract(scaledX);

    // Per-beam slow sinusoidal drift + static noise offset
    float drift  = sin(t * 1.4 + beamIdx * 1.2) * 0.05
                 + (hash(beamIdx * 3.7 + 1.1) - 0.5) * uNoiseIntensity * 0.22;
    float center = clamp(0.5 + drift, 0.05, 0.95);

    // Soft beam with smooth falloff
    float hw   = uBeamWidth * 0.5;
    float beam = smoothstep(hw, hw * 0.04, abs(localX - center));

    // Vertical vignette — fade at top and bottom edges
    float vig = smoothstep(0.0, 0.22, uv.y) * smoothstep(1.0, 0.78, uv.y);

    // Per-beam brightness variation
    float bright = 0.50 + 0.50 * hash(beamIdx * 5.3 + 7.9);

    float alpha = beam * vig * bright;
    gl_FragColor = vec4(uLightColor * alpha, alpha);
  }
`;

// ── Types ────────────────────────────────────────────────────────────────
export interface BeamsProps {
  beamWidth?: number;
  beamNumber?: number;
  lightColor?: string;
  speed?: number;
  noiseIntensity?: number;
  /** radians — 0.48 ≈ 27.5° diagonal */
  rotation?: number;
}

// ── Inner scene (mounts inside Canvas) ──────────────────────────────────
function BeamScene({
  beamWidth = 0.45,
  beamNumber = 11,
  lightColor = "#FF8FB8",
  speed = 1.2,
  noiseIntensity = 1.0,
  rotation = 0.48,
}: BeamsProps) {
  const matRef = useRef<THREE.ShaderMaterial>(null!);

  // Stable uniform object created once — R3F needs the same object reference
  // so it doesn't re-create the ShaderMaterial on every render.
  const uniforms = useMemo(
    () => ({
      uTime:           { value: 0 },
      uSpeed:          { value: speed },
      uBeamWidth:      { value: beamWidth },
      uBeamNumber:     { value: beamNumber },
      uLightColor:     { value: new THREE.Color(lightColor) },
      uNoiseIntensity: { value: noiseIntensity },
      uRotation:       { value: rotation },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useFrame((_, delta) => {
    if (matRef.current) {
      matRef.current.uniforms.uTime.value += delta;
    }
  });

  return (
    <ScreenQuad>
      <shaderMaterial
        ref={matRef}
        vertexShader={VERT}
        fragmentShader={FRAG}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </ScreenQuad>
  );
}

// ── Canvas wrapper (exported, lazy-loaded by AtmosphereBackground) ───────
export function BeamsCanvas(props: BeamsProps) {
  const [frameloop, setFrameloop] = useState<"always" | "never">("always");

  useEffect(() => {
    const onVisibility = () =>
      setFrameloop(document.hidden ? "never" : "always");
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return (
    <Canvas
      frameloop={frameloop}
      dpr={[1, 1.5]}
      gl={{ alpha: false, antialias: false, powerPreference: "low-power" }}
      style={{ width: "100%", height: "100%" }}
    >
      <color attach="background" args={["#F4F6F5"]} />
      <BeamScene {...props} />
    </Canvas>
  );
}
