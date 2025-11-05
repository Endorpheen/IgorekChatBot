import requests
import time
import statistics
import threading
import concurrent.futures
from datetime import datetime
import queue

BASE_URL = "http://localhost:8000"

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

def stress_test_step(rps: int, duration_seconds: int, endpoint: str = "/"):
    """Выполняем один шаг стресс-теста"""
    print(f"\n🚀 ТЕСТИРУЕМ {rps} RPS ({duration_seconds}s) - {endpoint}")
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
                                args=(results, duration_seconds, request_queue, endpoint))
        thread.start()
        threads.append(thread)

    # Мониторинг
    while any(thread.is_alive() for thread in threads):
        time.sleep(1)

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

def worker_thread(results, duration_seconds, request_queue, endpoint):
    """Рабочий поток"""
    start_time = time.time()

    while time.time() - start_time < duration_seconds:
        try:
            request_data = request_queue.get(timeout=1)
            if request_data is None:
                break

            request_start = time.time()
            response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
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

def find_knee_point(results_list):
    """Находим knee point - максимальный RPS без деградации"""
    if not results_list:
        return None, "Нет данных"

    # Ищем первый шаг, где P95 > 2× предыдущего ИЛИ есть ошибки > 1%
    for i in range(1, len(results_list)):
        current = results_list[i]
        previous = results_list[i-1]

        # Условие деградации: P95 > 2× предыдущего OR ошибки > 1%
        if (current['p95'] > previous['p95'] * 2) or (current['error_rate'] > 1):
            knee_point = previous['target_rps']
            reason = f"P95 вырос с {previous['p95']:.0f} до {current['p95']:.0f}ms (>2×) OR ошибки {current['error_rate']:.1f}%"
            return knee_point, reason

    # Если деградации нет, берем последний результат
    knee_point = results_list[-1]['target_rps']
    return knee_point, "Деградации не обнаружено"

def main():
    print("🎯 БЫСТРАЯ ПРОВЕРКА СТРЕСС-ТЕСТА")
    print("=" * 60)
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Эндпоинт: {BASE_URL}/ (контрольный 200-ответ)")

    # Проверяем доступность сервера
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print("❌ Сервер не доступен или не возвращает 200")
            return
        print(f"✅ Сервер доступен, возвращает {response.status_code}")
    except Exception as e:
        print(f"❌ Не удалось подключиться к серверу: {e}")
        return

    # Быстрый тест: 5 → 10 → 20 RPS
    rps_steps = [5, 10, 20]
    step_duration = 10  # 10 секунд на шаг

    results = []
    print(f"\n🔥 НАЧИНАЕМ БЫСТРЫЙ ТЕСТ: {' → '.join(map(str, rps_steps))} RPS")
    print(f"⏱️  Каждый шаг: {step_duration} секунд")

    for i, rps in enumerate(rps_steps):
        print(f"\n{'='*60}")
        print(f"ШАГ {i+1}/{len(rps_steps)}: {rps} RPS")

        result = stress_test_step(rps, step_duration, "/")
        if result:
            results.append(result)

            # Выводим одну строку как просили
            print(f"\n📈 {rps:3d} | {result['avg']:3.0f} {result['p95']:3.0f} {result['p99']:3.0f} | {result['error_rate']:4.1f}%")

            # Преждевременный выход если слишком много ошибок
            if result['error_rate'] > 10:
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
        print(f"   📈 Пропускная способность 'happy path' до деградации")
        print(f"   ⚡ P95 остается стабильным до этой точки")

        print(f"\n✅ ТЕСТ РАБОТАЕТ!")
    else:
        print(f"\n❌ Недостаточно данных для анализа knee point")

if __name__ == "__main__":
    main()