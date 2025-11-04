import type { Route } from '@playwright/test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const distDir = path.resolve(__dirname, '../../dist');
const assetCache = new Map<string, Buffer>();

const getContentType = (filePath: string): string => {
  const ext = path.extname(filePath).toLowerCase();
  switch (ext) {
    case '.html':
      return 'text/html; charset=utf-8';
    case '.js':
      return 'application/javascript; charset=utf-8';
    case '.css':
      return 'text/css; charset=utf-8';
    case '.svg':
      return 'image/svg+xml';
    case '.png':
      return 'image/png';
    case '.json':
      return 'application/json; charset=utf-8';
    case '.webp':
      return 'image/webp';
    default:
      return 'application/octet-stream';
  }
};

const readAsset = async (relativePath: string) => {
  const normalised = relativePath.replace(/^[/\\]+/, '');
  const targetPath = path.resolve(distDir, normalised);
  if (!targetPath.startsWith(distDir)) {
    throw new Error('Запрошен недопустимый путь');
  }
  if (!assetCache.has(targetPath)) {
    const data = await readFile(targetPath);
    assetCache.set(targetPath, data);
  }
  return assetCache.get(targetPath)!;
};

export const serveStaticApp = async (route: Route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (!url.hostname.includes('127.0.0.1')) {
    await route.continue();
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    await route.fallback();
    return;
  }

  if (
    url.pathname === '/' ||
    url.pathname === '/index.html' ||
    url.pathname === '/web-ui/' ||
    url.pathname === '/web-ui/index.html'
  ) {
    const html = await readAsset('index.html');
    await route.fulfill({
      status: 200,
      body: html,
      contentType: getContentType('index.html'),
    });
    return;
  }

  if (url.pathname.startsWith('/web-ui/')) {
    const assetPath = url.pathname.replace('/web-ui/', '');
    try {
      const asset = await readAsset(assetPath);
      await route.fulfill({
        status: 200,
        body: asset,
        contentType: getContentType(assetPath),
      });
    } catch {
      await route.fulfill({
        status: 404,
        body: `Not found: ${assetPath}`,
        contentType: 'text/plain; charset=utf-8',
      });
    }
    return;
  }

  await route.fallback();
};
