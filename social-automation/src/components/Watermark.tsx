import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { display, colors } from "../theme";

// Persistent brand lockup, top of frame.
export const Watermark: React.FC<{ handle: string }> = ({ handle }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [4, 16], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        top: 110,
        left: 0,
        right: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        opacity,
      }}
    >
      <Img src={staticFile("logo.png")} style={{ width: 64, height: 64, borderRadius: 14 }} />
      <span
        style={{
          fontFamily: display,
          fontWeight: 800,
          fontSize: 46,
          letterSpacing: "-0.01em",
          color: colors.text,
        }}
      >
        Primnox
      </span>
      <span
        style={{
          fontFamily: display,
          fontWeight: 700,
          fontSize: 30,
          color: colors.lavender,
          opacity: 0.85,
        }}
      >
        {handle}
      </span>
    </div>
  );
};
