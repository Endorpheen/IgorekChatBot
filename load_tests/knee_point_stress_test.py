import requests
import time
import statistics
import json
import base64
import hashlib
import hmac
import threading
import concurrent.futures
import sys
import os
from datetime import datetime, timedelta
import queue

# Добавляем путь к приложению для импорта настроек
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = "http://localhost:8000"

def get_signed_link_secret():
    """Получаем секрет из настроек приложения"""
    try:
        # Импортируем настройки приложения
        from app.settings import get_settings
        settings = get_settings()
        return settings.signed_link_secret
    except ImportError:
        # Если не удалось импортировать, читаем из .env файла
        try:
            with open('../.env', 'r') as f:
                for line in f:
                    if line.startswith('SIGNED_LINK_SECRET='):
                        return line.split('=', 1)[1].strip()
        except FileNotFoundError:
            pass

    # Фоллбэк на значение по умолчанию
    return "test-signed-link-secret"

class SignedLinkGenerator:
    """Генератор валидных signed links на основе анализа кода"""

    def __init__(self):
        self.secret = get_signed_link_secret().encode("utf-8")

    def _sign(self, data: bytes) -> str:
        """Создаем HMAC signature"""
        signature = hmac.new(self.secret, data, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    def generate_attachment_token(self, file_path: str, ttl_seconds: int = 3600) -> str:
        """Генерируем токен для chat-attachment"""
        payload = {
            "resource": "chat-attachment",
            "data": {
                "file_path": file_path
            },
            "exp": int(time.time()) + ttl_seconds,
        }

        # Сериализуем payload
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        # Кодируем и подписываем
        token = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        signature = self._sign(raw)

        return f"{token}.{signature}"

class KneePointTestResults:
    def __init__(self):
        self.response_times = []
        self.errors = 0
        self.timeouts = 0
        self.success_200 = 0
        self.client_errors = 0
        self.server_errors = 0
        self.status_codes = {}
        self.total_requests = 0
        self.lock = threading.Lock()

def stress_test_step(rps: int, duration_seconds: int, signed_url: str):
    """Выполняем один шаг стресс-теста"""
    print(f"\n🚀 ТЕСТИРУЕМ {rps} RPS ({duration_seconds}s)")
    print("=" * 50)

    num_threads = min(rps, 100)
    total_requests_needed = rps * duration_seconds

    # Создаем очередь запросов
    request_queue = queue.Queue()
    for i in range(total_requests_needed):
        request_queue.put({"request_id": i})

    results = KneePointTestResults()
    start_time = time.time()

    # Запуск рабочих потоков
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=worker_thread,
                                args=(results, duration_seconds, request_queue, signed_url))
        thread.start()
        threads.append(thread)

    # Мониторинг
    while any(thread.is_alive() for thread in threads):
        time.sleep(5)

    # Ожидание завершения
    for thread in threads:
        thread.join()

    # Расчет статистики
    actual_duration = time.time() - start_time
    actual_rps = results.total_requests / actual_duration if actual_duration > 0 else 0

    if results.response_times:
        avg = statistics.mean(results.response_times)
        median = statistics.median(results.response_times)
        p95 = sorted(results.response_times)[int(len(results.response_times) * 0.95)]
        p99 = sorted(results.response_times)[int(len(results.response_times) * 0.99)]
        error_rate = (results.errors / results.total_requests * 100) if results.total_requests > 0 else 0

        print(f"📊 РЕЗУЛЬТАТ {rps} RPS:")
        print(f"   📈 Фактический RPS: {actual_rps:.1f}")
        print(f"   ⚡ avg/p95/p99: {avg:.0f}/{p95:.0f}/{p99:.0f} ms")
        print(f"   ❌ Ошибки: {error_rate:.1f}%")
        print(f"   ✅ 200 ответы: {results.success_200}/{results.total_requests}")
        print(f"   📋 Статусы: {dict(sorted(results.status_codes.items()))}")

        return {
            'target_rps': rps,
            'actual_rps': actual_rps,
            'avg': avg,
            'p95': p95,
            'p99': p99,
            'error_rate': error_rate,
            'success_200': results.success_200,
            'total_requests': results.total_requests
        }
    else:
        print(f"❌ Нет данных для {rps} RPS")
        return None

def worker_thread(results, duration_seconds, request_queue, signed_url):
    """Рабочий поток"""
    start_time = time.time()

    while time.time() - start_time < duration_seconds:
        try:
            request_data = request_queue.get(timeout=1)
            if request_data is None:
                break

            request_start = time.time()
            response = requests.get(signed_url, timeout=10)
            request_end = time.time()

            response_time = (request_end - request_start) * 1000
            status = response.status_code

            with results.lock:
                results.response_times.append(response_time)
                results.total_requests += 1
                results.status_codes[status] = results.status_codes.get(status, 0) + 1

                if status == 200:
                    results.success_200 += 1
                elif status >= 500:
                    results.server_errors += 1
                    results.errors += 1
                elif status >= 400:
                    results.client_errors += 1
                    results.errors += 1

        except requests.exceptions.Timeout:
            with results.lock:
                results.timeouts += 1
                results.errors += 1
                results.total_requests += 1
        except queue.Empty:
            continue
        except Exception as e:
            with results.lock:
                results.errors += 1
                results.total_requests += 1

def create_test_file_and_url():
    """Создаем тестовый файл и генерируем валидный signed URL"""

    # Сначала создаем тестовый файл
    test_content = "A" * 1500  # ~1.5KB
    test_filename = f"load_test_file_{int(time.time())}.txt"

    try:
        # Сохраняем файл в директорию загрузок (эмулируем загрузку)
        import os
        os.makedirs("/tmp/test_uploads", exist_ok=True)
        test_file_path = f"/tmp/test_uploads/{test_filename}"

        with open(test_file_path, 'w') as f:
            f.write(test_content)

        print(f"✅ Создан тестовый файл: {test_file_path}")

        # Генерируем валидный signed URL
        generator = SignedLinkGenerator()
        token = generator.generate_attachment_token(test_file_path, ttl_seconds=7200)  # 2 часа

        signed_url = f"{BASE_URL}/signed/chat/attachments?token={token}"

        print(f"✅ Сгенерирован signed URL для файла")
        print(f"   📁 Файл: {test_file_path}")
        print(f"   🔗 URL: {signed_url[:100]}...")

        # Тестируем доступность
        response = requests.get(signed_url, timeout=10)
        print(f"   🧪 Тестовый запрос: {response.status_code}")

        if response.status_code == 200:
            print(f"   ✅ Signed URL РАБОТАЕТ - возвращает 200!")
            return signed_url
        else:
            print(f"   ❌ Signed URL не работает: {response.text[:100]}")
            return None

    except Exception as e:
        print(f"❌ Ошибка создания файла/URL: {e}")
        return None

def find_knee_point(results_list):
    """Находим knee point - максимальный RPS без деградации"""
    if not results_list:
        return None, "Нет данных"

    # Ищем первый шаг, где P95 > 2× предыдущего ИЛИ есть ошибки
    for i in range(1, len(results_list)):
        current = results_list[i]
        previous = results_list[i-1]

        # Условие деградации: P95 > 2× предыдущего OR есть ошибки
        if (current['p95'] > previous['p95'] * 2) or (current['error_rate'] > 1):
            knee_point = previous['target_rps']
            reason = f"P95 вырос с {previous['p95']:.0f} до {current['p95']:.0f}ms (>2×) OR ошибки {current['error_rate']:.1f}%"
            return knee_point, reason

    # Если деградации нет, берем последний результат
    knee_point = results_list[-1]['target_rps']
    return knee_point, "Деградации не обнаружено"

def main():
    print("🎯 СТУПЕНЧАТЫЙ СТРЕСС-ТЕСТ ДЛЯ ПОИСКА KNEE POINT")
    print("=" * 60)
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Проверяем доступность сервера
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print("❌ Сервер не доступен")
            return
        print(f"✅ Сервер доступен")
    except Exception as e:
        print(f"❌ Не удалось подключиться к серверу: {e}")
        return

    # Создаем валидный signed URL
    signed_url = create_test_file_and_url()
    if not signed_url:
        print("❌ Не удалось создать рабочий signed URL")
        return

    # Ступенчатый тест: 10 → 20 → 40 → 60 → 80 RPS
    rps_steps = [10, 20, 40, 60, 80]
    step_duration = 120  # 2 минуты на шаг

    results = []
    print(f"\n🔥 НАЧИНАЕМ СТУПЕНЧАТЫЙ ТЕСТ: {' → '.join(map(str, rps_steps))} RPS")

    for rps in rps_steps:
        result = stress_test_step(rps, step_duration, signed_url)
        if result:
            results.append(result)

            # Выводим одну строку как просили
            print(f"\n📈 {rps} | {result['avg']:.0f} {result['p95']:.0f} {result['p99']:.0f} | {result['error_rate']:.1f}%")

            # Преждевременный выход если слишком много ошибок
            if result['error_rate'] > 50:
                print(f"\n⚠️  Прерываем тест - слишком много ошибок ({result['error_rate']:.1f}%)")
                break
        else:
            print(f"\n❌ Шаг {rps} RPS не удался")
            break

    # Анализ knee point
    if len(results) >= 2:
        knee_rps, reason = find_knee_point(results)

        print(f"\n🎯 АНАЛИЗ KNEE POINT:")
        print(f"   📍 KNEE POINT: {knee_rps} RPS")
        print(f"   📊 Причина: {reason}")

        # Детальная сводка
        print(f"\n📋 ДЕТАЛЬНАЯ СВОДКА:")
        for result in results:
            print(f"   RPS {result['target_rps']:3d} | avg:{result['avg']:3.0f} p95:{result['p95']:3.0f} p99:{result['p99']:3.0f} | errors:{result['error_rate']:4.1f}% | 200:{result['success_200']:4d}")

        print(f"\n🏆 ИТОГ: Максимальный стабильный RPS = {knee_rps}")
    else:
        print(f"\n❌ Недостаточно данных для анализа knee point")

if __name__ == "__main__":
    main()