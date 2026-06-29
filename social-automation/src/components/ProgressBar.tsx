import { useCurrentFrame, useVideoConfig } from "remotion";
import { colors } from "../theme";

export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const pct = Math.min(1, frame / durationInFrames);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 70,
        left: 90,
        right: 90,
        height: 8,
        borderRadius: 999,
        backgroundColor: "rgba(240,237,230,0.14)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pct * 100}%`,
          height: "100%",
          borderRadius: 999,
          background: `linear-gradient(90deg, ${colors.lavender}, ${colors.warm})`,
        }}
      />
    </div>
  );
};
