import { expect, test } from '@playwright/test';
import { serveStaticApp } from './utils';

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
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Игорёк очень любит галлюцинации')).toBeVisible();

    const sortButton = page.getByTestId('thread-sort-toggle');
    const initialLabel = (await sortButton.textContent()) ?? '';
    await expect(sortButton).toBeVisible();
    await sortButton.click();
    const toggledText = initialLabel.includes('сверху') ? 'Новые снизу' : 'Новые сверху';
    await expect(sortButton).toHaveText(toggledText);

    await expect(page.locator('[data-thread-name="Главный тред"]')).toBeVisible();
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
    await page.waitForLoadState('networkidle');
    await page.getByTestId('nav-images').click();

    await expect(page).toHaveURL(/\/images$/);
    await expect(page.getByRole('button', { name: 'Сгенерировать' })).toBeVisible();

    await page.getByTestId('back-to-chat').click();
    await expect(page).toHaveURL('/');
  });
});
