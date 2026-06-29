import { AbsoluteFill, Sequence, staticFile } from "remotion";
import type { CalculateMetadataFunction } from "remotion";
import { Audio } from "@remotion/media";
import type { Caption } from "@remotion/captions";
import { fps, OUTRO_SEC } from "./theme";
import { Background } from "./components/Background";
import { Captions } from "./components/Captions";
import { Watermark } from "./components/Watermark";
import { ProgressBar } from "./components/ProgressBar";
import { Outro } from "./components/Outro";

export type Meta = {
  slug: string;
  title: string;
  hook: string;
  cta: string;
  voice: string;
  link: string;
  handle: string;
  music: string;
  durationSec: number;
  wordCount: number;
};

export type PrimnoxShortProps = {
  slug: string;
  meta: Meta | null;
  captions: Caption[] | null;
};

export const calculatePrimnoxMetadata: CalculateMetadataFunction<
  PrimnoxShortProps
> = async ({ props }) => {
  const dir = `render/${props.slug}`;
  const [meta, captions] = (await Promise.all([
    fetch(staticFile(`${dir}/meta.json`)).then((r) => r.json()),
    fetch(staticFile(`${dir}/captions.json`)).then((r) => r.json()),
  ])) as [Meta, Caption[]];

  const durationInFrames = Math.ceil((meta.durationSec + OUTRO_SEC) * fps);

  return {
    durationInFrames,
    fps,
    props: { ...props, meta, captions },
    defaultOutName: props.slug,
  };
};

export const PrimnoxShort: React.FC<PrimnoxShortProps> = ({ slug, meta, captions }) => {
  if (!meta || !captions) return null;

  const narrationFrames = Math.round(meta.durationSec * fps);

  return (
    <AbsoluteFill>
      <Background />

      {/* Voiceover */}
      <Audio src={staticFile(`render/${slug}/audio.mp3`)} />
      {/* Optional background music — drop a file in public/music/ and set `music:` in the script */}
      {meta.music ? (
        <Audio src={staticFile(`music/${meta.music}`)} volume={0.1} />
      ) : null}

      <Watermark handle={meta.handle} />

      {/* Captions run for the length of the narration */}
      <Sequence durationInFrames={narrationFrames}>
        <Captions captions={captions} />
      </Sequence>

      <ProgressBar />

      {/* End card after narration finishes */}
      <Sequence from={narrationFrames}>
        <Outro cta={meta.cta} link={meta.link} />
      </Sequence>
    </AbsoluteFill>
  );
};
