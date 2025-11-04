import { expect, test } from '@playwright/test';
import { serveStaticApp } from './utils';

const ONE_BY_ONE_PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAoMBgVKS0dYAAAAASUVORK5CYII=';
const stagingBase = process.env.PLAYWRIGHT_IMAGE_STAGING_BASE_URL;
const stagingApiKey = process.env.PLAYWRIGHT_IMAGE_STAGING_API_KEY;

test.describe('Генерация изображений', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', serveStaticApp);
  });

  test('детерминированная генерация через моки', async ({ page }) => {
    test.skip('TODO(frontend): вернуть после стабилизации провижена ключа и моделей');
    await page.addInitScript(() => {
      window.localStorage.setItem('image-enabled-providers', JSON.stringify({ together: true }));
      window.localStorage.setItem('imageGenerationProvider', 'together');
      window.__keyReady = false;
      const request = indexedDB.open('togetherKeyDB', 2);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('keys')) {
          db.createObjectStore('keys', { keyPath: 'id' });
        }
      };
      request.onsuccess = () => {
        const db = request.result;
        const tx = db.transaction('keys', 'readwrite');
        tx.objectStore('keys').put({
          id: 'provider:together',
          providerId: 'together',
          encrypted: false,
          key: 'mock-key',
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        });
        tx.oncomplete = () => {
          db.close();
          window.__keyReady = true;
        };
      };
    });

    await page.route('**/image/providers', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          providers: [
            { id: 'together', label: 'Together AI', enabled: true, recommended_models: [], requires_key: true },
          ],
        }),
      });
    });

    await page.route('**/image/providers/together/models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          models: [
            {
              id: 'mock-model',
              display_name: 'Mock Model',
              limits: { min_steps: 1, max_steps: 50, min_cfg: 1, max_cfg: 10 },
              defaults: { width: 1024, height: 1024, steps: 28, cfg: 4.5 },
              capabilities: { supports_seed: true },
            },
          ],
        }),
      });
    });

    await page.route('**/image/jobs', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'mock-job' }),
      });
    });

    await page.route('**/image/jobs/mock-job', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'done',
          provider: 'together',
          model: 'mock-model',
          width: 1024,
          height: 1024,
          steps: 28,
          duration_ms: 3200,
          result_url: '/downloads/generated.png',
        }),
      });
    });

    await page.route('**/downloads/generated.png', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: Buffer.from(ONE_BY_ONE_PNG_BASE64, 'base64'),
      });
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('nav-images').click();
    await page.waitForFunction(() => window.__keyReady === true);

    await page.getByLabel('Промпт').fill('Золотой закат над морем');
    await page.getByRole('button', { name: 'Сгенерировать' }).click();

    await expect(page.getByText('Генерация')).toBeVisible();
    await expect(page.getByRole('img', { name: 'Результат генерации' })).toBeVisible();
    const downloadLink = page.getByRole('link', { name: 'Скачать WEBP' });
    await expect(downloadLink).toHaveAttribute('href', expect.stringContaining('/downloads/generated.png'));
  });

  test('генерация через staging API', async ({ page }) => {
    test.skip(!stagingBase || !stagingApiKey, 'Staging API не настроен');

    await page.addInitScript(({ base }) => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input: RequestInfo, init?: RequestInit) => {
        if (typeof input === 'string' && input.includes('/api/')) {
          const url = new URL(input, window.location.origin);
          const baseUrl = new URL(base);
          url.protocol = baseUrl.protocol;
          url.host = baseUrl.host;
          url.pathname = `${baseUrl.pathname.replace(/\/$/, '')}${url.pathname}`;
          return originalFetch(url.toString(), init);
        }
        return originalFetch(input, init);
      };
      window.localStorage.setItem('image-enabled-providers', JSON.stringify({ together: true }));
      window.localStorage.setItem('imageGenerationProvider', 'together');
    }, { base: stagingBase });

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.getByTestId('nav-images').click();

    await page.getByRole('button', { name: 'Настройки' }).click();
    await page.getByLabel('API Key').fill(stagingApiKey ?? '');
    await page.getByRole('button', { name: 'Сохранить' }).click();
    await page.waitForTimeout(500);
    await page.locator('.settings-overlay').click({ position: { x: 10, y: 10 } });

    await page.getByLabel('Промпт').fill('Staging smoke');
    await page.getByRole('button', { name: 'Сгенерировать' }).click();

    await expect(page.getByRole('img', { name: 'Результат генерации' })).toBeVisible();
  });
});
