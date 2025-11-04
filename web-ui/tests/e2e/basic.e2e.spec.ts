import { expect, test } from '@playwright/test';
import type { Route } from '@playwright/test';
import path from 'node:path';
import { readFile } from 'node:fs/promises';

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

const serveStaticApp = async (route: Route) => {
  const { request } = route;
  const url = new URL(request.url());
  if (!url.hostname.includes('127.0.0.1')) {
    await route.continue();
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    await route.fallback();
    return;
  }

  if (url.pathname === '/' || url.pathname === '/index.html' || url.pathname === '/web-ui/' || url.pathname === '/web-ui/index.html') {
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

test.describe('Фронтенд: smoke-навигация', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', serveStaticApp);
  });

  test('открывает чат и позволяет переключать сортировку тредов', async ({ page }) => {
    await page.route('**/api/**', async (route) => {
      const request = route.request();
      if (request.method() === 'GET' && request.url().includes('/api/image/providers')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ providers: [] }),
          contentType: 'application/json',
        });
        return;
      }
      if (request.method() === 'GET') {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({}),
          contentType: 'application/json',
        });
        return;
      }
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ ok: true }),
        contentType: 'application/json',
      });
    });

    await page.goto('/');

    await expect(page.getByText('Игорёк очень любит галлюцинации')).toBeVisible();

    const sortButton = page.getByRole('button', { name: /Новые/ });
    const initialLabel = await sortButton.innerText();
    await sortButton.click();
    await expect(sortButton).toBeVisible();
    await expect(sortButton).not.toHaveText(initialLabel);

    await expect(page.getByRole('button', { name: 'Главный тред' })).toBeVisible();
  });

  test('навигация к генерации изображений показывает панель настроек', async ({ page }) => {
    await page.route('**/api/image/providers**', async (route) => {
      if (route.request().url().includes('provider=')) {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ models: [] }),
          contentType: 'application/json',
        });
        return;
      }
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          providers: [
            { id: 'together', label: 'Together AI', enabled: true, recommended_models: [], requires_key: false },
          ],
        }),
        contentType: 'application/json',
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Генерация' }).click();

    await expect(page).toHaveURL(/\/images$/);
    await expect(page.getByRole('button', { name: 'Сгенерировать' })).toBeVisible();

    await page.getByRole('button', { name: '← В чат' }).click();
    await expect(page).toHaveURL('/');
  });
});
