const DEFAULT_DEV_ORIGINS = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
];

export function parseAllowedOrigins(rawValue) {
  if (!rawValue) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (Array.isArray(parsed)) {
      return parsed
        .filter((value) => typeof value === "string" && value.trim().length > 0)
        .map((value) => value.trim());
    }
  } catch {
    // fall through to comma separated parsing
  }

  return rawValue
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildOriginMatcher(pattern) {
  if (pattern === "*") {
    return () => true;
  }

  if (pattern.includes("*")) {
    const regex = new RegExp(`^${pattern.split("*").map(escapeRegex).join(".*")}$`);
    return (origin) => regex.test(origin);
  }

  return (origin) => origin === pattern;
}

export function resolveAllowedOrigins(env = process.env) {
  const envAllowed = parseAllowedOrigins(env.CORS_ALLOWED_ORIGINS);
  const fallbackOrigins = [];

  if (envAllowed.length === 0 && env.APP_PUBLIC_ORIGIN) {
    fallbackOrigins.push(env.APP_PUBLIC_ORIGIN.trim());
  }

  if (
    envAllowed.length === 0 &&
    fallbackOrigins.length === 0 &&
    (env.NODE_ENV || "").toLowerCase() !== "production"
  ) {
    fallbackOrigins.push(...DEFAULT_DEV_ORIGINS);
  }

  const combined = [...envAllowed, ...fallbackOrigins].filter(Boolean);
  const unique = [...new Set(combined)];
  const sanitized = unique.filter((origin) => origin !== "*");
  const hadWildcard = sanitized.length !== unique.length;

  return {
    origins: sanitized,
    hadWildcard,
  };
}

export function createCorsOptions({ env = process.env, logger = console } = {}) {
  const { origins, hadWildcard } = resolveAllowedOrigins(env);
  if (hadWildcard) {
    logger.warn("Ignoring insecure wildcard entry in CORS_ALLOWED_ORIGINS.");
  }

  const matchers = origins.map(buildOriginMatcher);

  function originValidator(origin, callback) {
    if (!origin) {
      return callback(null, true);
    }

    if (matchers.length === 0) {
      logger.warn(`Blocked CORS request (no allowed origins configured): ${origin}`);
      return callback(null, false);
    }

    const isAllowed = matchers.some((matcher) => matcher(origin));
    if (isAllowed) {
      return callback(null, true);
    }

    logger.warn(`Blocked CORS request from origin: ${origin}`);
    return callback(null, false);
  }

  return {
    allowedOrigins: origins,
    origin: originValidator,
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
  };
}

