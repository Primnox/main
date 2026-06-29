import "./index.css";
import { Composition } from "remotion";
import { fps } from "./theme";
import { PrimnoxShort, calculatePrimnoxMetadata } from "./Video";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PrimnoxShort"
      component={PrimnoxShort}
      durationInFrames={300}
      fps={fps}
      width={1080}
      height={1920}
      defaultProps={{ slug: "example", meta: null, captions: null }}
      calculateMetadata={calculatePrimnoxMetadata}
    />
  );
};
