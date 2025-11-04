import { expect, test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { serveStaticApp } from './utils';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const fixturesDir = path.resolve(__dirname, 'fixtures');

const attachmentResponse = {
  status: 'ok',
  response: 'Документ обработан: готово',
  attachments: [
    {
      filename: 'processed.txt',
      url: '/downloads/processed.txt',
      content_type: 'text/plain',
      size: 32,
      description: 'Результат обработки',
    },
  ],
};

test.describe('Фронтенд: чат и история', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', serveStaticApp);
  });

  test('полный цикл с документом и скачиванием результата', async ({ page }) => {
    test.skip('TODO(frontend): восстановить e2e после исправления mock-а document chat flow');
    await page.route('**/file/analyze', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', response: 'Документ принят', thread_id: 'default' }),
      });
    });

    await page.route('**/chat', async (route) => {
      const request = route.request();
      const body = await request.postDataJSON();
      expect(body.message).toContain('проанализируй');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(attachmentResponse),
      });
    });

    await page.route('**', async (route) => {
      const url = route.request().url();
      if (url.includes('/chat') || url.includes('/file/analyze') || url.includes('/downloads/processed.txt')) {
        await route.fallback();
        return;
      }
      if (url.startsWith('http://127.0.0.1:4173')) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.route('**/downloads/processed.txt', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/plain; charset=utf-8',
        body: 'Processed attachment content',
      });
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const filePath = path.join(fixturesDir, 'sample.txt');
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Прикрепить файл' }).click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(filePath);

    await expect(page.getByText('sample.txt')).toBeVisible();
    await expect(page.getByText('Ожидает запроса')).toBeVisible();

    const chatResponsePromise = page.waitForResponse((response) => response.url().includes('/chat') && response.request().method() === 'POST');
    await page.getByPlaceholder('Введите команду или запрос...').fill('проанализируй документ');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await chatResponsePromise;

    await expect(page.getByText('Документ обработан: готово')).toBeVisible();
    const attachmentLink = page.getByTestId('chat-attachment-download').first();
    await expect(attachmentLink).toBeVisible();

    const [downloadPage] = await Promise.all([
      page.waitForEvent('popup'),
      attachmentLink.click(),
    ]);

    await downloadPage.waitForLoadState('domcontentloaded');
    const downloadContent = await downloadPage.locator('body').innerText();
    expect(downloadContent?.trim()).toBe('Processed attachment content');
    await downloadPage.close();
  });

  test('история сообщений восстанавливается после перезагрузки', async ({ page }) => {
    await page.route('**/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', response: 'Ответ бота', thread_id: 'default' }),
      });
    });

    await page.route('**', async (route) => {
      const url = route.request().url();
      if (url.includes('/chat')) {
        await route.fallback();
        return;
      }
      if (url.startsWith('http://127.0.0.1:4173')) {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const chatResponsePromise = page.waitForResponse((response) => response.url().includes('/chat') && response.request().method() === 'POST');
    await page.getByPlaceholder('Введите команду или запрос...').fill('Привет!');
    await page.getByRole('button', { name: 'Отправить' }).click();
    await chatResponsePromise;
    await expect(page.getByText('Ответ бота')).toBeVisible();

    // Дать времени очереди сохранения записать сообщения в IndexedDB
    await page.waitForTimeout(200);

    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.getByText('Привет!')).toBeVisible();
    await expect(page.getByText('Ответ бота')).toBeVisible();
  });
});
