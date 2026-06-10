import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { createReadStream, existsSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";

const root = resolve(process.argv[2] || ".");
const port = Number(process.env.PORT || 5173);
const host = "127.0.0.1";
const proxyPrefix = "/api";
const defaultApiUpstream = "https://functioning-element-pushing-whenever.trycloudflare.com";

const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml"
};

function resolveRequest(url) {
  const pathname = decodeURIComponent(new URL(url, `http://${host}:${port}`).pathname);
  const safePath = normalize(pathname).replace(/^(\.\.[/\\])+/, "");
  let filePath = join(root, safePath);

  if (!existsSync(filePath) || statSync(filePath).isDirectory()) {
    filePath = join(root, "index.html");
  }

  if (!filePath.startsWith(root)) {
    return null;
  }

  return filePath;
}

function normalizeUpstream(value) {
  const candidate = String(value || "").trim().replace(/\/$/, "");
  if (!candidate) return defaultApiUpstream;

  try {
    const parsed = new URL(candidate);
    if (!["http:", "https:"].includes(parsed.protocol)) {
      return null;
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

function apiTargetUrl(requestUrl, upstreamBase) {
  const incoming = new URL(requestUrl || "/", `http://${host}:${port}`);
  const upstreamPath = incoming.pathname.slice(proxyPrefix.length) || "/";
  return new URL(`${upstreamPath}${incoming.search}`, upstreamBase);
}

function stripHopByHopHeaders(headers) {
  const result = { ...headers };
  [
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "origin",
    "referer",
    "x-projectpilot-upstream"
  ].forEach((name) => {
    delete result[name];
  });
  return result;
}

function proxyApi(request, response) {
  if (request.method === "OPTIONS") {
    response.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-ProjectPilot-Upstream",
      "Access-Control-Max-Age": "600",
      "Cache-Control": "no-store"
    });
    response.end();
    return;
  }

  const upstreamHeader = Array.isArray(request.headers["x-projectpilot-upstream"])
    ? request.headers["x-projectpilot-upstream"][0]
    : request.headers["x-projectpilot-upstream"];
  const upstreamBase = normalizeUpstream(upstreamHeader || process.env.API_UPSTREAM_BASE || defaultApiUpstream);

  if (!upstreamBase) {
    response.writeHead(400, {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    });
    response.end(JSON.stringify({ detail: "Invalid API upstream" }));
    return;
  }

  const target = apiTargetUrl(request.url, upstreamBase);
  const transport = target.protocol === "https:" ? httpsRequest : httpRequest;
  const headers = stripHopByHopHeaders(request.headers);

  const proxyRequest = transport(
    target,
    {
      method: request.method,
      headers
    },
    (proxyResponse) => {
      const responseHeaders = {
        ...proxyResponse.headers,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store"
      };
      response.writeHead(proxyResponse.statusCode || 502, responseHeaders);
      proxyResponse.pipe(response);
    }
  );

  proxyRequest.on("error", (error) => {
    response.writeHead(502, {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
    });
    response.end(JSON.stringify({ detail: error.message || "API proxy failed" }));
  });

  request.pipe(proxyRequest);
}

const server = createServer((request, response) => {
  const pathname = new URL(request.url || "/", `http://${host}:${port}`).pathname;
  if (pathname === proxyPrefix || pathname.startsWith(`${proxyPrefix}/`)) {
    proxyApi(request, response);
    return;
  }

  const filePath = resolveRequest(request.url || "/");

  if (!filePath || !existsSync(filePath)) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }

  response.writeHead(200, {
    "Content-Type": mime[extname(filePath)] || "application/octet-stream",
    "Cache-Control": "no-store"
  });
  createReadStream(filePath).pipe(response);
});

server.listen(port, host, () => {
  console.log(`ProjectPilot preview running at http://${host}:${port}`);
});

server.on("error", (error) => {
  if (error && error.code === "EADDRINUSE" && process.env.ALLOW_PORT_IN_USE === "1") {
    console.log(`ProjectPilot preview port ${port} is already in use; reusing the existing server.`);
    process.exit(0);
    return;
  }

  throw error;
});
