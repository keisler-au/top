import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../dist", import.meta.url));
const port = Number.parseInt(process.env.FRONTEND_PORT ?? "4173", 10);
const apiTarget = process.env.API_BASE_URL ?? "http://localhost:8000";

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
]);

function safeFilePath(pathname) {
  const decoded = decodeURIComponent(pathname).replace(/^\/+/, "");
  const candidate = normalize(join(root, decoded));
  return candidate === root || candidate.startsWith(`${root}/`)
    ? candidate
    : null;
}

async function proxyApi(request, response) {
  const target = new URL(request.url ?? "/", apiTarget);
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers)) {
    if (value !== undefined && name !== "host") {
      headers.set(name, Array.isArray(value) ? value.join(", ") : value);
    }
  }
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD"
      ? undefined
      : request,
    duplex: "half",
  });
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");
  responseHeaders.delete("transfer-encoding");
  response.writeHead(upstream.status, Object.fromEntries(responseHeaders));
  if (upstream.body) {
    for await (const chunk of upstream.body) {
      response.write(chunk);
    }
  }
  response.end();
}

async function serveStatic(request, response) {
  const requestUrl = new URL(request.url ?? "/", "http://localhost");
  let filePath = safeFilePath(requestUrl.pathname);
  if (!filePath) {
    response.writeHead(400).end("Invalid path");
    return;
  }

  try {
    if ((await stat(filePath)).isDirectory()) {
      filePath = join(filePath, "index.html");
    }
    await stat(filePath);
  } catch {
    filePath = join(root, "index.html");
  }

  response.writeHead(200, {
    "Content-Type": contentTypes.get(extname(filePath)) ?? "application/octet-stream",
    // Development assets are not content-hashed, so every response must be
    // revalidated or a rebuilt module can remain stale in the browser.
    "Cache-Control": "no-cache",
  });
  createReadStream(filePath).pipe(response);
}

createServer(async (request, response) => {
  try {
    if (request.url?.startsWith("/api/")) {
      request.url = request.url.slice(4) || "/";
      await proxyApi(request, response);
      return;
    }
    await serveStatic(request, response);
  } catch (error) {
    response.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
    response.end(error instanceof Error ? error.message : "Request failed");
  }
}).listen(port, () => {
  process.stdout.write(`Dashboard available at http://localhost:${port}\n`);
});
