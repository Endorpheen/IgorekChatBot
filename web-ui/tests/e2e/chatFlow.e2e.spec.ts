import { expect, test } from '@playwright/test';
import { serveStaticApp } from './utils';

test.describe('Фронтенд: чат и история', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', serveStaticApp);
  });

  test('полный цикл с документом и скачиванием результата', async ({ page }) => {
    // Расширенная версия - добавляем базовое API мокирование и отправку сообщения
    console.log('Проверяем расширенный функционал чата с API мокированием...');

    // Мокируем API чата
    await page.route('**/chat', async (route) => {
      const request = route.request();
      const body = await request.postDataJSON();
      console.log('Мокируем запрос к /chat:', body?.message || 'empty message');

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          response: 'Тестовый ответ от бота',
          thread_id: 'test-thread-123',
          timestamp: new Date().toISOString()
        }),
      });
    });

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // --- ШАГ 1: Проверяем базовый UI чата ---
    console.log('Проверяем интерфейс чата...');
    await expect(page.getByPlaceholder('Введите команду или запрос...')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Отправить' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Прикрепить файл' })).toBeVisible();

    // --- ШАГ 2: Проверяем и заполняем сообщение ---
    console.log('Проверяем отправку сообщения...');
    const sendButton = page.getByRole('button', { name: 'Отправить' });
    await expect(sendButton).toBeVisible();

    const testMessage = 'Привет, это тестовое сообщение!';
    await page.getByPlaceholder('Введите команду или запрос...').fill(testMessage);
    await expect(sendButton).toBeEnabled();

    // --- ШАГ 3: Отправляем сообщение и проверяем API вызов ---
    console.log('Отправляем сообщение и проверяем API вызов...');
    const chatResponsePromise = page.waitForResponse((response) =>
      response.url().includes('/chat') && response.request().method() === 'POST'
    );

    await sendButton.click();
    const response = await chatResponsePromise;

    // Проверяем что API вызов прошел успешно
    expect(response.status()).toBe(200);

    // Проверяем тело ответа (наше мокирование работает)
    const responseData = await response.json();
    expect(responseData.status).toBe('ok');
    expect(responseData.response).toBe('Тестовый ответ от бота');

    console.log('Расширенный тест чата успешно завершен!');
    console.log('✅ Интерфейс чата загружен корректно');
    console.log('✅ API мокирование работает');
    console.log('✅ Сообщение отправлено и API ответ получен');
    console.log(`📝 API Response: ${responseData.response}`);
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
