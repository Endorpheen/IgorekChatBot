import fs from "fs/promises";
import path from "path";

const DEFAULT_ALLOWED_EXTENSIONS = new Set([".md", ".markdown", ".mdx", ".txt", ".json", ".canvas"]);

class VaultAccessError extends Error {
  constructor(message, reason, data) {
    super(message);
    this.name = "VaultAccessError";
    this.reason = reason;
    this.data = data ?? null;
  }
}

const ensureBaseSuffix = (base) => (base.endsWith(path.sep) ? base : `${base}${path.sep}`);

export function createVaultReader(baseDir, options = {}) {
  if (!baseDir || typeof baseDir !== "string") {
    throw new Error("baseDir is required");
  }

  const normalizedBase = path.resolve(baseDir);
  const allowedExtensions = options.allowedExtensions
    ? new Set(Array.from(options.allowedExtensions, (ext) => ext.toLowerCase()))
    : DEFAULT_ALLOWED_EXTENSIONS;

  let resolvedBasePathPromise;

  const getResolvedBasePath = async () => {
    if (!resolvedBasePathPromise) {
      resolvedBasePathPromise = fs.realpath(normalizedBase);
    }
    return resolvedBasePathPromise;
  };

  const ensureWithinBase = (candidate, base) => {
    if (candidate === base) {
      return true;
    }
    const baseWithSep = ensureBaseSuffix(base);
    return candidate.startsWith(baseWithSep);
  };

  const resolveFilePath = async (relativeId) => {
    if (typeof relativeId !== "string" || !relativeId.trim()) {
      throw new VaultAccessError("Invalid path", "invalid_input", { id: relativeId });
    }

    if (relativeId.includes("\0")) {
      throw new VaultAccessError("Path contains invalid characters", "invalid_input", { id: relativeId });
    }

    const basePath = await getResolvedBasePath();
    const sanitized = relativeId.replace(/\\/g, "/");
    const candidate = path.resolve(basePath, sanitized);

    if (!ensureWithinBase(candidate, basePath)) {
      throw new VaultAccessError("Access outside of vault is forbidden", "outside_of_base", { id: relativeId });
    }

    const extension = path.extname(candidate).toLowerCase();
    if (!allowedExtensions.has(extension)) {
      throw new VaultAccessError("File type is not allowed", "extension_not_allowed", {
        id: relativeId,
        extension,
      });
    }

    let realPath;
    try {
      realPath = await fs.realpath(candidate);
    } catch (error) {
      if (error?.code === "ENOENT" || error?.code === "ENOTDIR") {
        throw error;
      }
      throw new VaultAccessError("Failed to resolve path", "resolution_failed", {
        id: relativeId,
        cause: error?.message || String(error),
      });
    }

    if (!ensureWithinBase(realPath, basePath)) {
      throw new VaultAccessError("Access outside of vault is forbidden", "outside_of_base", { id: relativeId });
    }

    return realPath;
  };

  const readFile = async (relativeId) => {
    const fullPath = await resolveFilePath(relativeId);
    return fs.readFile(fullPath, "utf-8");
  };

  return {
    readFile,
    resolveFilePath,
    getResolvedBasePath,
    allowedExtensions,
  };
}

export { VaultAccessError, DEFAULT_ALLOWED_EXTENSIONS };
