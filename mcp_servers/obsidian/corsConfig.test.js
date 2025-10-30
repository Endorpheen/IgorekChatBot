import { test } from "node:test";
import assert from "node:assert/strict";
import { parseAllowedOrigins, resolveAllowedOrigins, createCorsOptions } from "./corsConfig.js";

const noopLogger = {
  warn() {},
};

function runOriginCheck(options, origin) {
  return new Promise((resolve, reject) => {
    options.origin(origin, (error, allow) => {
      if (error) {
        reject(error);
      } else {
        resolve(allow);
      }
    });
  });
}

test("parseAllowedOrigins корректно разбирает JSON-массив и список через запятую", () => {
  assert.deepEqual(parseAllowedOrigins('["https://a.com","https://b.com"]'), ["https://a.com", "https://b.com"]);
  assert.deepEqual(parseAllowedOrigins(" https://a.com , https://b.com "), ["https://a.com", "https://b.com"]);
});

test("resolveAllowedOrigins использует APP_PUBLIC_ORIGIN как запасной вариант", () => {
  const result = resolveAllowedOrigins({
    CORS_ALLOWED_ORIGINS: "",
    APP_PUBLIC_ORIGIN: "https://app.example.com",
    NODE_ENV: "production",
  });

  assert.deepEqual(result, {
    origins: ["https://app.example.com"],
    hadWildcard: false,
  });
});

test("resolveAllowedOrigins добавляет дев-ориджины в непроизводительной среде", () => {
  const result = resolveAllowedOrigins({
    CORS_ALLOWED_ORIGINS: "",
    APP_PUBLIC_ORIGIN: "",
    NODE_ENV: "development",
  });

  assert.ok(result.origins.includes("http://localhost:3000"));
  assert.equal(result.hadWildcard, false);
});

test("createCorsOptions игнорирует wildcard и разрешает только ожидаемые домены", async () => {
  const warnings = [];
  const logger = {
    warn: (msg) => warnings.push(msg),
  };

  const options = createCorsOptions({
    env: {
      CORS_ALLOWED_ORIGINS: '["https://safe.example.com","*","https://*.example.net"]',
    },
    logger,
  });

  assert.deepEqual(options.allowedOrigins.sort(), ["https://safe.example.com", "https://*.example.net"].sort());
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Ignoring insecure wildcard/);

  assert.equal(await runOriginCheck(options, "https://safe.example.com"), true);
  assert.equal(await runOriginCheck(options, "https://foo.example.net"), true);
  assert.equal(await runOriginCheck(options, "https://example.net"), false);
});

test("createCorsOptions блокирует сторонние домены при пустом allow-list в проде", async () => {
  const options = createCorsOptions({
    env: {
      NODE_ENV: "production",
    },
    logger: noopLogger,
  });

  assert.deepEqual(options.allowedOrigins, []);
  assert.equal(await runOriginCheck(options, "https://evil.example.org"), false);
});

test("createCorsOptions пропускает запросы без origin", async () => {
  const options = createCorsOptions({
    env: {
      CORS_ALLOWED_ORIGINS: '["https://safe.example.com"]',
    },
    logger: noopLogger,
  });

  assert.equal(await runOriginCheck(options, undefined), true);
});

