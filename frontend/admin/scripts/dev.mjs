import { createHash } from "node:crypto";
import { readdir, readFile, rename, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = join(root, "dist");
const staging = join(root, ".dev-build-next");
const previous = join(root, ".dev-build-previous");
let stopping = false;
let build = null;
let server = null;

// Poll file contents so bind-mounted edits work on Docker Desktop as well as
// Linux. Watch only source/config/assets; emitted files cannot trigger a loop.
async function fingerprint() {
  const hash = createHash("sha256");
  async function add(relative) {
    const path = join(root, relative);
    try {
      const entries = await readdir(path, { withFileTypes: true });
      entries.sort((a, b) => a.name.localeCompare(b.name));
      for (const entry of entries) if (entry.isFile() || entry.isDirectory()) await add(join(relative, entry.name));
    } catch (error) {
      if (error.code === "ENOENT") { hash.update(relative + ":missing"); return; }
      if (error.code !== "ENOTDIR") throw error;
      hash.update(relative);
      try { hash.update(await readFile(path)); }
      catch (readError) { if (readError.code !== "ENOENT") throw readError; hash.update(":missing"); }
    }
  }
  for (const path of ["src", "index.html", "tsconfig.json", "public", "scripts/build.mjs"]) await add(path);
  return hash.digest("hex");
}

async function rebuild() {
  process.stdout.write("Building dashboard…\n");
  build = spawn(process.execPath, ["scripts/build.mjs"], {
    cwd: root, stdio: "inherit", detached: process.platform !== "win32", env: { ...process.env, FRONTEND_BUILD_DIR: staging },
  });
  const code = await new Promise((resolve, reject) => {
    build.once("error", reject); build.once("exit", resolve);
  });
  build = null;
  if (stopping) return;
  if (code !== 0) {
    process.stderr.write("Dashboard build failed. Keeping the last successful build; fix the source to retry.\n");
    return;
  }
  await rm(previous, { recursive: true, force: true });
  try { await rename(dist, previous); } catch (error) { if (error.code !== "ENOENT") throw error; }
  await rename(staging, dist);
  await rm(previous, { recursive: true, force: true });
  process.stdout.write("Dashboard updated. Refresh your browser.\n");
  if (!server) {
    server = spawn(process.execPath, ["scripts/serve.mjs"], { cwd: root, stdio: "inherit" });
    server.once("exit", code => {
      if (!stopping) { process.stderr.write("Dashboard server stopped.\n"); stop(code ?? 1); }
    });
  }
}

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  if (build) {
    try {
      if (process.platform === "win32") build.kill("SIGTERM");
      else process.kill(-build.pid, "SIGTERM");
    } catch (error) { if (error.code !== "ESRCH") throw error; }
  }
  server?.kill("SIGTERM");
  // Child handles keep Node alive until their exits have been collected.
  process.exitCode = code;
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());

try {
  let last = "";
  while (!stopping) {
    const next = await fingerprint();
    if (next !== last) { last = next; await rebuild(); }
    if (!stopping) await new Promise(resolve => setTimeout(resolve, 500));
  }
} catch (error) {
  process.stderr.write(`Dashboard development watcher failed: ${error.message}\n`);
  stop(1);
}
