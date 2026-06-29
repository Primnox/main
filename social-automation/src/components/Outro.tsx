import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { display, body, colors } from "../theme";

// End card shown for the final stretch (after narration ends). Big logo, CTA, link.
export const Outro: React.FC<{ cta: string; link: string }> = ({ cta, link }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 14 });
  const y = interpolate(enter, [0, 1], [70, 0]);
  const opacity = interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(60% 50% at 50% 45%, ${colors.lavender}1f, ${colors.bg} 75%)`,
        justifyContent: "center",
        alignItems: "center",
        opacity,
      }}
    >
      <div
        style={{
          transform: `translateY(${y}px)`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 34,
          paddingInline: 100,
          textAlign: "center",
        }}
      >
        <Img src={staticFile("logo.png")} style={{ width: 200, height: 200, borderRadius: 44 }} />
        <div
          style={{
            fontFamily: display,
            fontWeight: 800,
            fontSize: 84,
            lineHeight: 1.05,
            letterSpacing: "-0.02em",
            color: colors.text,
          }}
        >
          {cta}
        </div>
        <div
          style={{
            fontFamily: body,
            fontWeight: 700,
            fontSize: 48,
            color: colors.bg,
            backgroundColor: colors.warm,
            padding: "16px 40px",
            borderRadius: 999,
          }}
        >
          {link}
        </div>
      </div>
    </AbsoluteFill>
  );
};
