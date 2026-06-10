import { defineConfig } from "vite";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

const proxyPrefix = "/api";
const defaultApiUpstream = "https://functioning-element-pushing-whenever.trycloudflare.com";

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

function apiTargetUrl(requestUrl, upstreamBase, host = "127.0.0.1", port = 5173) {
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

function projectPilotApiProxy() {
  return {
    name: "projectpilot-api-proxy",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        proxyApi(request, response, next, 5173);
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((request, response, next) => {
        proxyApi(request, response, next, 4173);
      });
    }
  };
}

function proxyApi(request, response, next, port) {
  const pathname = new URL(request.url || "/", `http://127.0.0.1:${port}`).pathname;
  if (pathname !== proxyPrefix && !pathname.startsWith(`${proxyPrefix}/`)) {
    next();
    return;
  }

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

  const target = apiTargetUrl(request.url, upstreamBase, "127.0.0.1", port);
  const transport = target.protocol === "https:" ? httpsRequest : httpRequest;
  const proxyRequest = transport(
    target,
    {
      method: request.method,
      headers: stripHopByHopHeaders(request.headers)
    },
    (proxyResponse) => {
      response.writeHead(proxyResponse.statusCode || 502, {
        ...proxyResponse.headers,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store"
      });
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

export default defineConfig({
  base: "./",
  plugins: [projectPilotApiProxy()],
  server: {
    port: 5173,
    strictPort: false,
    host: "127.0.0.1"
  },
  preview: {
    port: 4173,
    host: "127.0.0.1"
  },
  build: {
    outDir: "dist",
    emptyOutDir: true
  }
});
