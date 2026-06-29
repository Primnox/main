// Full pipeline: script -> voiceover + captions -> rendered vertical mp4.
//   node tools/make.mjs <slug>        (or)  npm run make -- <slug>
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const slug = process.argv[2] || "example";
const isWin = process.platform === "win32";

function run(cmd, args) {
  console.log(`\n$ ${cmd} ${args.join(" ")}\n`);
  const r = spawnSync(cmd, args, { cwd: root, stdio: "inherit", shell: isWin });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

mkdirSync(resolve(root, "out"), { recursive: true });

// 1. Generate voiceover + captions + caption pack from the script.
run(isWin ? "python" : "python3", ["tools/generate.py", slug]);

// 2. Render the video. Props (the slug) are read from the generated props.json.
const propsFile = `public/render/${slug}/props.json`;
if (!existsSync(resolve(root, propsFile))) {
  console.error(`Missing ${propsFile} — did step 1 fail?`);
  process.exit(1);
}
run("npx", [
  "remotion",
  "render",
  "PrimnoxShort",
  `out/${slug}.mp4`,
  `--props=${propsFile}`,
]);

console.log(`\n✓ Done.\n  Video:   out/${slug}.mp4\n  Caption: out/${slug}.captions.md\n  Post it 🚀`);
