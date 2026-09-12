"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef, type MutableRefObject } from "react";
import * as THREE from "three";

/**
 * The hero scene. Two things, both bound to data:
 *
 *  - a dust field whose visible density is the day's aerosol optical depth
 *    and whose drift is the day's wind;
 *  - a photovoltaic array whose glass carries the soiling the storm model
 *    computed for that day, washed by rain and by cleaning.
 *
 * The scene reads a mutable `frame` ref every tick so scrolling or replaying
 * never re-renders React; the caller writes the day's values into it.
 */
export interface SceneFrame {
  density: number; // 0..1, AOD relative to the record's high
  soiling: number; // 0..0.3, transmission loss on the array
  wind: number; // m/s
  wash: number; // 0..1, flash after a rain or cleaning event
}

const DUST_VERT = /* glsl */ `
  uniform float uTime;
  uniform float uDensity;
  uniform float uWind;
  uniform float uPixelRatio;
  attribute float aSeed;
  attribute float aSize;
  varying float vAlpha;
  varying float vSeed;

  void main() {
    vSeed = aSeed;
    // Only a density-dependent share of particles is "airborne" today.
    float visible = step(aSeed, uDensity);
    vec3 p = position;
    float t = uTime * (0.15 + 0.35 * fract(aSeed * 7.31));
    // Downwind drift with a slow vertical wobble; wraps inside the box.
    p.x = mod(p.x + t * (0.6 + uWind * 0.35) + aSeed * 3.0, 24.0) - 12.0;
    p.y += sin(t * 1.7 + aSeed * 40.0) * 0.35;
    p.z = mod(p.z + t * 0.2 * uWind, 30.0) - 22.0;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float depth = clamp(-mv.z / 30.0, 0.0, 1.0);
    gl_PointSize = aSize * uPixelRatio * (1.0 - 0.6 * depth) * (14.0 / max(-mv.z, 1.0));
    vAlpha = visible * (0.55 - 0.4 * depth) * (0.35 + 0.65 * smoothstep(0.0, 0.5, uDensity));
  }
`;

const DUST_FRAG = /* glsl */ `
  varying float vAlpha;
  varying float vSeed;
  void main() {
    vec2 c = gl_PointCoord - 0.5;
    float d = dot(c, c);
    if (d > 0.25) discard;
    float soft = smoothstep(0.25, 0.0, d);
    vec3 sand = mix(vec3(0.88, 0.64, 0.35), vec3(0.62, 0.40, 0.18), fract(vSeed * 3.7));
    gl_FragColor = vec4(sand, vAlpha * soft);
  }
`;

const PANEL_VERT = /* glsl */ `
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec2 vUv;
  varying float vInstance;
  void main() {
    vUv = uv;
    vInstance = float(gl_InstanceID);
    vec4 world = instanceMatrix * vec4(position, 1.0);
    vNormal = normalize(mat3(modelMatrix) * mat3(instanceMatrix) * normal);
    vec4 mv = viewMatrix * modelMatrix * world;
    vView = -mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const PANEL_FRAG = /* glsl */ `
  uniform float uSoiling;
  uniform float uWash;
  uniform float uTime;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec2 vUv;
  varying float vInstance;

  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
  }

  void main() {
    vec3 n = normalize(vNormal);
    vec3 v = normalize(vView);
    float fresnel = pow(1.0 - max(dot(n, v), 0.0), 3.0);
    // Cell grid: the module's 6 x 10 cells, thin busbars between them.
    vec2 cell = fract(vUv * vec2(6.0, 10.0));
    float bus = smoothstep(0.0, 0.04, cell.x) * smoothstep(0.0, 0.04, cell.y)
              * smoothstep(1.0, 0.96, cell.x) * smoothstep(1.0, 0.96, cell.y);
    vec3 glass = mix(vec3(0.05, 0.08, 0.14), vec3(0.10, 0.16, 0.30), bus);
    vec3 sky = vec3(0.35, 0.42, 0.55);
    vec3 color = glass + sky * fresnel * 0.55;
    // Dust: an ochre film, patchy, thicker toward the lower edge where it settles.
    float film = noise(vUv * 9.0 + vInstance * 0.37) * 0.6 + noise(vUv * 31.0 + vInstance) * 0.4;
    float settle = 0.7 + 0.3 * (1.0 - vUv.y);
    float dust = clamp(uSoiling / 0.30, 0.0, 1.0) * settle * (0.55 + 0.45 * film);
    vec3 ochre = vec3(0.72, 0.52, 0.28);
    color = mix(color, ochre, dust * 0.85);
    // Wash: a brief cool sheen sweeping down after rain or a clean.
    float sweep = smoothstep(0.0, 0.25, uWash) * smoothstep(1.0, 0.6, uWash);
    float band = smoothstep(0.08, 0.0, abs((1.0 - vUv.y) - (1.0 - uWash)));
    color += vec3(0.55, 0.75, 1.0) * sweep * band * 0.6;
    gl_FragColor = vec4(color, 1.0);
  }
`;

function DustField({ frame, count }: { frame: MutableRefObject<SceneFrame>; count: number }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const { gl } = useThree();
  const geometry = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    const sizes = new Float32Array(count);
    let s = 1234567;
    const rnd = () => {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
    for (let i = 0; i < count; i++) {
      positions[i * 3] = rnd() * 24 - 12;
      positions[i * 3 + 1] = rnd() * 9 - 2.5;
      positions[i * 3 + 2] = rnd() * 30 - 22;
      seeds[i] = rnd();
      sizes[i] = 0.6 + rnd() * 1.8;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    g.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    return g;
  }, [count]);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uDensity: { value: 0.3 },
      uWind: { value: 2 },
      uPixelRatio: { value: Math.min(gl.getPixelRatio(), 1.5) },
    }),
    [gl],
  );
  useFrame(({ clock }) => {
    const m = material.current;
    if (!m) return;
    m.uniforms.uTime.value = clock.elapsedTime;
    m.uniforms.uDensity.value += (frame.current.density - m.uniforms.uDensity.value) * 0.08;
    m.uniforms.uWind.value += (frame.current.wind - m.uniforms.uWind.value) * 0.08;
  });
  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        vertexShader={DUST_VERT}
        fragmentShader={DUST_FRAG}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function SolarArray({ frame }: { frame: MutableRefObject<SceneFrame> }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const material = useRef<THREE.ShaderMaterial>(null);
  const rows = 6;
  const cols = 14;
  const count = rows * cols;
  const uniforms = useMemo(() => ({ uSoiling: { value: 0 }, uWash: { value: 0 }, uTime: { value: 0 } }), []);
  const matrices = useMemo(() => {
    const dummy = new THREE.Object3D();
    const out: THREE.Matrix4[] = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        dummy.position.set((c - (cols - 1) / 2) * 1.16, -1.85 + r * 0.02, -1.6 - r * 2.4);
        dummy.rotation.set(-Math.PI / 2 + THREE.MathUtils.degToRad(25), 0, 0);
        dummy.scale.set(1.08, 1.0, 1);
        dummy.updateMatrix();
        out.push(dummy.matrix.clone());
      }
    }
    return out;
  }, []);
  useFrame(({ clock }) => {
    const m = mesh.current;
    if (m && !m.userData.placed) {
      matrices.forEach((mat, i) => m.setMatrixAt(i, mat));
      m.instanceMatrix.needsUpdate = true;
      m.userData.placed = true;
    }
    const s = material.current;
    if (!s) return;
    s.uniforms.uSoiling.value += (frame.current.soiling - s.uniforms.uSoiling.value) * 0.1;
    s.uniforms.uWash.value = frame.current.wash;
    s.uniforms.uTime.value = clock.elapsedTime;
  });
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]} frustumCulled={false}>
      <planeGeometry args={[1, 1.9]} />
      <shaderMaterial ref={material} uniforms={uniforms} vertexShader={PANEL_VERT} fragmentShader={PANEL_FRAG} side={THREE.DoubleSide} />
    </instancedMesh>
  );
}

function Ground() {
  // A faint warm horizon so the array sits on something rather than in a void.
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.9, -8]}>
        <planeGeometry args={[80, 60]} />
        <meshBasicMaterial color="#151009" />
      </mesh>
      <mesh position={[0, -0.6, -30]}>
        <planeGeometry args={[90, 6]} />
        <meshBasicMaterial color="#3a2612" transparent opacity={0.35} />
      </mesh>
    </group>
  );
}

export function DustScene({
  frame,
  particles = 12000,
  active = true,
  onContextLost,
}: {
  frame: MutableRefObject<SceneFrame>;
  particles?: number;
  active?: boolean;
  onContextLost?: () => void;
}) {
  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [0, 1.15, 5.2], fov: 50, near: 0.1, far: 80 }}
      gl={{ antialias: false, powerPreference: "high-performance", alpha: false }}
      frameloop={active ? "always" : "demand"}
      style={{ position: "absolute", inset: 0 }}
      aria-hidden
      onCreated={({ gl }) => {
        // A lost context must never leave a white rectangle: hand the hero back
        // to its static fallback instead.
        gl.domElement.addEventListener("webglcontextlost", (event) => {
          event.preventDefault();
          onContextLost?.();
        });
      }}
    >
      <color attach="background" args={["#0f0d0a"]} />
      <fog attach="fog" args={["#0f0d0a", 6, 26]} />
      <Ground />
      <SolarArray frame={frame} />
      <DustField frame={frame} count={particles} />
    </Canvas>
  );
}
