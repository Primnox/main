import { useMemo } from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  createTikTokStyleCaptions,
  type Caption,
  type TikTokPage,
} from "@remotion/captions";
import { body, colors } from "../theme";

// Higher = more words per page; lower = snappier word-by-word.
const SWITCH_CAPTIONS_EVERY_MS = 900;

export const Captions: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const { fps } = useVideoConfig();

  const { pages } = useMemo(
    () =>
      createTikTokStyleCaptions({
        captions,
        combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS,
      }),
    [captions],
  );

  return (
    <AbsoluteFill>
      {pages.map((page, index) => {
        const next = pages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = Math.min(
          next ? (next.startMs / 1000) * fps : Infinity,
          startFrame + (SWITCH_CAPTIONS_EVERY_MS / 1000) * fps,
        );
        const durationInFrames = endFrame - startFrame;
        if (durationInFrames <= 0) return null;

        return (
          <Sequence key={index} from={startFrame} durationInFrames={durationInFrames}>
            <CaptionPage page={page} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const CaptionPage: React.FC<{ page: TikTokPage }> = ({ page }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 7 });
  const scale = interpolate(enter, [0, 1], [0.86, 1]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  const absoluteTimeMs = page.startMs + (frame / fps) * 1000;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        paddingInline: 90,
        transform: `translateY(40px)`,
      }}
    >
      <div
        style={{
          fontFamily: body,
          fontWeight: 700,
          fontSize: 96,
          lineHeight: 1.12,
          textAlign: "center",
          letterSpacing: "-0.02em",
          whiteSpace: "pre-wrap",
          color: colors.text,
          transform: `scale(${scale})`,
          opacity,
          textShadow: "0 6px 28px rgba(0,0,0,0.85)",
        }}
      >
        {page.tokens.map((token) => {
          const isActive = token.fromMs <= absoluteTimeMs && token.toMs > absoluteTimeMs;
          return (
            <span
              key={`${token.fromMs}-${token.text}`}
              style={{
                color: isActive ? colors.bg : colors.text,
                backgroundColor: isActive ? colors.lavender : "transparent",
                borderRadius: 14,
                padding: isActive ? "0 10px" : "0",
                boxDecorationBreak: "clone",
                WebkitBoxDecorationBreak: "clone",
              }}
            >
              {token.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
