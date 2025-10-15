import express from "express";
import fs from "fs/promises";
import fssync from "fs";
import path from "path";
import jwt from "jsonwebtoken";
import cors from "cors";

const app = express();
app.use(express.json());

// --- CORS support ---
const corsOptions = {
  origin: "*",
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization"],
};
app.use(cors(corsOptions));

// --- Обработка preflight до авторизации ---
app.options("*", cors(corsOptions), (req, res) => {
  res.sendStatus(204);
});

const VAULT_PATH = process.env.VAULT_PATH || "/vault";
const LOG_FILE = process.env.LOG_FILE || "/app/logs.json";
const MCP_SECRET = process.env.MCP_SECRET || "";

// --- Auth config ---
const JWT_SECRET = process.env.JWT_SECRET || "";
const REQUIRE_JWT = String(process.env.REQUIRE_JWT).toLowerCase() === "true";
const AUTH_TOKEN_LEGACY = process.env.AUTH_TOKEN_LEGACY || process.env.AUTH_TOKEN || "";

// --- Auth middleware (JWT + legacy) ---
app.use((req, res, next) => {
  if (req.method === "OPTIONS") {
    return res.sendStatus(204);
  }

  // 🔓 Token check temporarily disabled for testing SSE connection
  return next();

  // const token = req.headers.authorization?.split(" ")[1];
  // if (token !== process.env.AUTH_TOKEN) {
  //   return res.status(403).json({ error: "Forbidden" });
  // }

  // const authHeader = req.headers["authorization"] || "";
  // const bearer = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;
  // const queryToken = req.query?.auth;
  //
  // if (!REQUIRE_JWT && AUTH_TOKEN_LEGACY) {
  //   if ((bearer && bearer === AUTH_TOKEN_LEGACY) || (queryToken && queryToken === AUTH_TOKEN_LEGACY)) {
  //     return next();
  //   }
  // }
  //
  // if (!bearer) {
  //   return res.status(401).json({
  //     error: REQUIRE_JWT ? "JWT required" : "Missing Authorization header",
  //   });
  // }
  //
  // try {
  //   const decoded = jwt.verify(bearer, JWT_SECRET);
  //   req.user = decoded;
  //   return next();
  // } catch (e) {
  //   console.error("JWT verification failed:", e.message);
  //   return res.status(403).json({ error: "Invalid or expired token" });
  // }
});

// --- Logger ---
async function writeLog(entry) {
  const logEntry = {
    timestamp: new Date().toISOString(),
    ...entry,
  };

  let logs = [];
  try {
    if (fssync.existsSync(LOG_FILE)) {
      const data = await fs.readFile(LOG_FILE, "utf-8");
      logs = JSON.parse(data);
    }
  } catch {
    logs = [];
  }

  logs.push(logEntry);

  try {
    await fs.writeFile(LOG_FILE, JSON.stringify(logs, null, 2));
  } catch (e) {
    console.error("Failed to write log:", e.message);
  }
}

// --- Helpers ---
function parseSince(str) {
  if (!str) return null;
  const num = parseInt(str.slice(0, -1));
  const unit = str.slice(-1);
  if (unit === "d") return num * 86400 * 1000;
  if (unit === "h") return num * 3600 * 1000;
  if (unit === "m") return num * 60 * 1000;
  return null;
}

async function searchVault(query, since) {
  if (!query && !since) return [];
  let results = [];
  const now = Date.now();
  const sinceMs = parseSince(since);

  async function walk(dir) {
    const files = await fs.readdir(dir, { withFileTypes: true });
    for (const file of files) {
      const fullPath = path.join(dir, file.name);
      if (file.isDirectory()) {
        await walk(fullPath);
      } else if (file.name.endsWith(".md")) {
        const stats = await fs.stat(fullPath);

        if (sinceMs && now - stats.mtimeMs > sinceMs) continue;

        const content = await fs.readFile(fullPath, "utf-8");
        if ((query && (file.name.includes(query) || content.includes(query))) || !query) {
          results.push({
            id: path.relative(VAULT_PATH, fullPath),
            title: file.name,
            path: path.relative(VAULT_PATH, fullPath),
            snippet: content.slice(0, 200),
            modified: stats.mtime.toISOString(),
          });
        }
      }
    }
  }
  await walk(VAULT_PATH);
  return results;
}

async function fetchFile(id) {
  if (!id) throw new Error("No id");
  const fullPath = path.join(VAULT_PATH, id);
  const content = await fs.readFile(fullPath, "utf-8");
  return content;
}

class McpError extends Error {
  constructor(message, code, data) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

const safeStringify = (value) => {
  try {
    return JSON.stringify(value);
  } catch {
    return "[unserializable]";
  }
};

async function handleSearch(params = {}) {
  const query = typeof params.query === "string" ? params.query : "";
  const since = typeof params.since === "string" ? params.since : null;
  const results = await searchVault(query, since);
  await writeLog({ action: "search", params, results: results.length });
  return results.map((item) => ({
    id: item.id,
    title: item.title,
    path: item.path,
    snippet: item.snippet,
    modified: item.modified,
  }));
}

async function handleFetch(params = {}) {
  const id = typeof params.id === "string" ? params.id.trim() : "";
  if (!id) {
    throw new McpError("Invalid params: id is required", -32602, { field: "id" });
  }

  try {
    const content = await fetchFile(id);
    await writeLog({ action: "fetch", params: { id }, results: 1 });
    return { id, content };
  } catch (error) {
    if (error.code === "ENOENT" || error.code === "ENOTDIR") {
      await writeLog({ action: "fetch", params: { id }, results: 0, error: "not_found" });
      throw new McpError("File not found", -32004, { id });
    }
    throw error;
  }
}

const resolveToolCall = (method, params = {}) => {
  const rawMethod = typeof method === "string" ? method.trim() : "";
  if (!rawMethod) {
    return { toolName: "", toolParams: {} };
  }

  if (rawMethod === "tools/call") {
    const toolName = params?.name ?? params?.toolName ?? params?.tool?.name ?? "";
    const toolParams = params?.arguments ?? params?.args ?? params?.tool?.arguments ?? {};
    return { toolName, toolParams };
  }

  return { toolName: rawMethod, toolParams: params ?? {} };
};

async function runTool(method, params = {}) {
  const { toolName, toolParams } = resolveToolCall(method, params);
  const rawName = typeof toolName === "string" ? toolName.trim() : "";
  if (!rawName) {
    throw new McpError("Unknown tool", -32601, { name: toolName || method });
  }

  const name = rawName.toLowerCase();
  console.log(`[MCP] Executing tool '${rawName}' with params: ${safeStringify(toolParams)}`);

  switch (name) {
    case "search":
      return handleSearch(toolParams);
    case "fetch":
      return handleFetch(toolParams);
    default:
      throw new McpError("Unknown tool", -32601, { name: rawName });
  }
}

const respondOk = (res, id, result) => {
  res.json({ jsonrpc: "2.0", id: id ?? null, result });
};

const respondError = (res, id, error) => {
  const payload = {
    jsonrpc: "2.0",
    id: id ?? null,
    error: {
      code: typeof error?.code === "number" ? error.code : -32000,
      message: error?.message || "Server error",
      data: error?.data ?? null,
    },
  };
  res.json(payload);
};

const ensureSecret = (req, res) => {
  if (!MCP_SECRET) {
    return true;
  }
  const authHeader = req.headers["authorization"] || "";
  const bearer = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;
  if (bearer === MCP_SECRET) {
    return true;
  }
  res.status(403).json({ error: "Forbidden" });
  return false;
};

app.post("/search", async (req, res) => {
  if (!ensureSecret(req, res)) {
    return;
  }
  try {
    const results = await handleSearch(req.body || {});
    res.json({ results });
  } catch (error) {
    console.error("[MCP] /search failed", error);
    res.status(500).json({ error: error?.message || "Search failed" });
  }
});

app.post("/fetch", async (req, res) => {
  if (!ensureSecret(req, res)) {
    return;
  }
  try {
    const result = await handleFetch(req.body || {});
    res.json(result);
  } catch (error) {
    if (error instanceof McpError) {
      return res.status(404).json({ error: error.message, code: error.code, data: error.data });
    }
    console.error("[MCP] /fetch failed", error);
    res.status(500).json({ error: error?.message || "Fetch failed" });
  }
});

const handleJsonRpcToolCall = async (req, res) => {
  const msg = req.body;
  if (!msg || msg.jsonrpc !== "2.0" || !msg.method) {
    return res.status(400).json({ error: "Invalid JSON-RPC" });
  }

  try {
    const result = await runTool(msg.method, msg.params);
    respondOk(res, msg.id, result);
  } catch (error) {
    if (error instanceof McpError) {
      return respondError(res, msg.id, error);
    }
    console.error("[MCP] Tool execution failed", error);
    return respondError(res, msg.id, new McpError("Server error", -32000));
  }
};

// --- MCP over SSE ---
app.get("/sse", (req, res) => {
  res.set({
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    "MCP-Protocol-Version": "2025-06-18",
  });

  res.write(
    `data: ${JSON.stringify({
      jsonrpc: "2.0",
      method: "initialized",
    })}\n\n`,
  );

  req.on("close", () => {
    res.end();
  });
});

app.post("/sse", async (req, res) => {
  const msg = req.body;

  if (!msg || msg.jsonrpc !== "2.0" || !msg.method) {
    return res.status(400).json({ error: "Invalid JSON-RPC" });
  }

  const ok = (resultObj) => res.json({ jsonrpc: "2.0", id: msg.id, result: resultObj });
  const err = (code, message, data) =>
    res.json({ jsonrpc: "2.0", id: msg.id ?? null, error: { code, message, data } });

  try {
    switch (msg.method) {
      case "initialize":
        return ok({
          protocolVersion: "2025-06-18",
          serverInfo: { name: "mcp-vault", version: "1.2.0" },
          capabilities: { tools: {} },
        });

      case "tools/list":
        return ok({
          tools: [
            {
              name: "search",
              description: "Search notes in vault (supports optional since filter)",
              inputSchema: {
                type: "object",
                properties: {
                  query: { type: "string" },
                  since: { type: "string", description: "Время: 7d, 12h, 30m" },
                },
                required: [],
              },
            },
            {
              name: "fetch",
              description: "Fetch note by id",
              inputSchema: {
                type: "object",
                properties: {
                  id: { type: "string" },
                },
                required: ["id"],
              },
            },
          ],
        });

      case "tools/call": {
        try {
          const result = await runTool(msg.method, msg.params);
          return ok({
            content: [{ type: "json", json: result }],
          });
        } catch (error) {
          if (error instanceof McpError) {
            return err(error.code ?? -32000, error.message ?? "Unknown tool", error.data ?? { name });
          }
          console.error("[MCP] tools/call failed", error);
          return err(-32000, "Server error", String(error?.message || error));
        }
      }

      default:
        return err(-32601, "Method not found", { method: msg.method });
    }
  } catch (e) {
    return err(-32000, "Server error", String(e?.message || e));
  }
});

app.post("/", handleJsonRpcToolCall);
app.post("/run", handleJsonRpcToolCall);

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`MCP Vault Server listening on ${PORT}`));
