// Primnox brand tokens + fonts (loaded once, blocks render until ready).
import { loadFont as loadSyne } from "@remotion/google-fonts/Syne";
import { loadFont as loadDM } from "@remotion/google-fonts/DMSans";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

export const display = loadSyne("normal", { weights: ["700", "800"] }).fontFamily;
export const body = loadDM("normal", { weights: ["400", "500", "700"] }).fontFamily;
export const mono = loadMono("normal", { weights: ["400", "700"] }).fontFamily;

export const colors = {
  bg: "#070707",
  text: "#f0ede6",
  lavender: "#c3c0ff", // primary
  warm: "#ffb695", // accent
  green: "#34d399",
  dim: "rgba(240,237,230,0.55)",
};

export const fps = 30;
export const OUTRO_SEC = 1.9; // end card after the narration finishes
