import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { colors } from "../theme";

// Animated Primnox-brand backdrop: deep black base, slow-drifting lavender/warm
// orbs, and a faint grid. Pure frame-driven animation (no CSS transitions).
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();

  const t = frame / durationInFrames;
  const orbA = {
    x: width * (0.2 + 0.12 * Math.sin(t * Math.PI * 2)),
    y: height * (0.26 + 0.05 * Math.cos(t * Math.PI * 2)),
  };
  const orbB = {
    x: width * (0.82 + 0.1 * Math.cos(t * Math.PI * 2 + 1)),
    y: height * (0.78 + 0.06 * Math.sin(t * Math.PI * 2 + 1)),
  };

  const grid = interpolate(frame, [0, 40], [0, 0.06], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(60% 45% at ${orbA.x}px ${orbA.y}px, ${colors.lavender}33, transparent 70%)`,
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(55% 40% at ${orbB.x}px ${orbB.y}px, ${colors.warm}26, transparent 70%)`,
        }}
      />
      {/* faint grid */}
      <AbsoluteFill
        style={{
          opacity: grid,
          backgroundImage: `linear-gradient(${colors.text} 1px, transparent 1px), linear-gradient(90deg, ${colors.text} 1px, transparent 1px)`,
          backgroundSize: "90px 90px",
          maskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
          WebkitMaskImage: "radial-gradient(circle at 50% 45%, black, transparent 80%)",
        }}
      />
      {/* vignette for caption legibility */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(70% 60% at 50% 52%, transparent 40%, rgba(0,0,0,0.55) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};
