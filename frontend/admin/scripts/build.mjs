import { cp, mkdir, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const projectRoot = new URL("../", import.meta.url);
const dist = process.env.FRONTEND_BUILD_DIR
  ? pathToFileURL(resolve(process.env.FRONTEND_BUILD_DIR) + sep)
  : new URL("../dist/", import.meta.url);

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

const compiler = process.platform === "win32" ? "tsc.cmd" : "tsc";
const result = spawnSync(compiler, ["-p", "tsconfig.json", "--outDir", fileURLToPath(new URL("assets/", dist))], {
  cwd: projectRoot,
  stdio: "inherit",
});
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

await cp(new URL("../index.html", import.meta.url), new URL("index.html", dist));
await cp(new URL("../src/styles", import.meta.url), new URL("styles", dist), {
  recursive: true,
});

const publicDirectory = new URL("../public", import.meta.url);
try {
  await cp(publicDirectory, dist, { recursive: true });
} catch (error) {
  if (!(error instanceof Error) || !error.message.includes("ENOENT")) {
    throw error;
  }
}
