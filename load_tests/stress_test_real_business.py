import requests
import time
import statistics
import json
import hashlib
import threading
import concurrent.futures
from datetime import datetime, timedelta
import queue

BASE_URL = "http://localhost:8000"

def generate_realistic_token(file_path="test.txt"):
    """Генерируем токен для реального эндпоинта"""
    timestamp = str(int(time.time()))
    signature = hashlib.md5(f'{file_path}:{timestamp}'.encode()).hexdigest()
    return f"{timestamp}:{signature}"

class StressTestResults:
    def __init__(self):
        self.response_times = []
        self.errors = 0
        self.timeouts = 0
        self.success_200 = 0
        self.client_errors = 0
        self.server_errors = 0
        self.status_codes = {}
        self.start_time = None
        self.end_time = None
        self.total_requests = 0
        self.lock = threading.Lock()

def worker_thread(results, duration_seconds, request_queue):
    """Рабочий поток для выполнения запросов"""
    start_time = time.time()

    while time.time() - start_time < duration_seconds:
        try:
            request_data = request_queue.get(timeout=1)
            if request_data is None:  # Сигнал завершения
                break

            file_path = request_data["file_path"]
            token = generate_realistic_token(file_path)
            params = {"token": token, "file_path": file_path}

            request_start = time.time()
            response = requests.get(f"{BASE_URL}/signed/chat/attachments",
                                  params=params,
                                  timeout=10)
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

def run_stress_test(target_rps=50, duration_minutes=5):
    """Запуск стресс-теста с заданным RPS и длительностью"""
    duration_seconds = duration_minutes * 60
    print(f"🚀 СТРЕСС-ТЕСТ: {target_rps} RPS, {duration_minutes} минут")
    print("=" * 60)
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Цель: /signed/chat/attachments (реальная бизнес-логика)")

    # Подготовка запросов
    num_threads = min(target_rps, 100)  # Ограничим число потоков
    total_requests_needed = target_rps * duration_seconds

    # Создаем очередь запросов
    request_queue = queue.Queue()
    for i in range(total_requests_needed):
        request_queue.put({"file_path": f"test_file_{i}.txt"})

    results = StressTestResults()
    results.start_time = time.time()

    # Запуск рабочих потоков
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=worker_thread, args=(results, duration_seconds, request_queue))
        thread.start()
        threads.append(thread)

    # Мониторинг прогресса
    last_report_time = time.time()
    last_request_count = 0

    while any(thread.is_alive() for thread in threads):
        time.sleep(10)  # Отчет каждые 10 секунд

        current_time = time.time()
        elapsed = current_time - results.start_time
        current_rps = (results.total_requests - last_request_count) / (current_time - last_report_time)

        print(f"⏱️  {elapsed:.0f}s | Запросов: {results.total_requests} | Текущий RPS: {current_rps:.1f} | Ошибки: {results.errors}")

        last_report_time = current_time
        last_request_count = results.total_requests

    # Ожидание завершения всех потоков
    for thread in threads:
        thread.join()

    results.end_time = time.time()

    # Расчет статистики
    total_duration = results.end_time - results.start_time
    actual_rps = results.total_requests / total_duration if total_duration > 0 else 0

    if results.response_times:
        avg = statistics.mean(results.response_times)
        median = statistics.median(results.response_times)
        p95 = sorted(results.response_times)[int(len(results.response_times) * 0.95)]
        p99 = sorted(results.response_times)[int(len(results.response_times) * 0.99)]
        min_time = min(results.response_times)
        max_time = max(results.response_times)
        error_rate = (results.errors / results.total_requests * 100) if results.total_requests > 0 else 0

        print(f"\n📊 РЕЗУЛЬТАТЫ СТРЕСС-ТЕСТА:")
        print(f"   🎯 Целевой RPS: {target_rps}")
        print(f"   📈 Фактический RPS: {actual_rps:.1f}")
        print(f"   ⏱️  Длительность: {total_duration:.1f}s (план {duration_seconds}s)")
        print(f"   🔢 Всего запросов: {results.total_requests}")
        print(f"   ⚡ avg/median/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽 min/max: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ✅ 200 ответы: {results.success_200}/{results.total_requests} ({(results.success_200/results.total_requests*100):.1f}%)")
        print(f"   ❌ Ошибки: {results.errors}/{results.total_requests} ({error_rate:.1f}%)")
        print(f"   🏥 5xx: {results.server_errors}")
        print(f"   ⚠️  4xx: {results.client_errors}")
        print(f"   ⏰ Таймауты: {results.timeouts}")
        print(f"   📋 Статусы: {dict(sorted(results.status_codes.items()))}")

        # Итоговая строка
        print(f"\n🎯 ИТОГ: ENDPOINT /signed/chat/attachments | RPS:{actual_rps:.0f} | {avg:.0f}/{p95:.0f}/{p99:.0f}ms | errors:{error_rate:.1f}%")

        return {
            'target_rps': target_rps,
            'actual_rps': actual_rps,
            'avg': avg,
            'median': median,
            'p95': p95,
            'p99': p99,
            'min': min_time,
            'max': max_time,
            'error_rate': error_rate,
            'total_requests': results.total_requests,
            'duration': total_duration,
            'success_200': results.success_200,
            'errors': results.errors,
            'server_errors': results.server_errors,
            'client_errors': results.client_errors,
            'timeouts': results.timeouts,
            'status_codes': results.status_codes
        }
    else:
        print("\n❌ Все запросы завершились с ошибками!")
        return None

def main():
    print("🔥 СТРЕСС-ТЕСТ ПРОДУКТИВНОСТИ С РЕАЛЬНОЙ БИЗНЕС-ЛОГИКОЙ")
    print("=" * 70)

    # Проверяем доступность сервера
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        if response.status_code != 200:
            print("❌ Сервер не доступен или отвечает некорректно")
            return
        print(f"✅ Сервер доступен (статус: {response.status_code})")
    except Exception as e:
        print(f"❌ Не удалось подключиться к серверу: {e}")
        print("💡 Запустите сервер: source .venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
        return

    # Запуск стресс-теста
    result = run_stress_test(target_rps=50, duration_minutes=5)

    if result:
        print(f"\n🎉 СТРЕСС-ТЕСТ ЗАВЕРШЕН!")
        print(f"🏆 ПРОИЗВОДИТЕЛЬНОСТЬ: {result['actual_rps']:.0f} RPS стабильной нагрузки")
        print(f"🛡️  НАДЕЖНОСТЬ: {result['error_rate']:.1f}% ошибок при реальной бизнес-логике")
        print(f"⚡ СКОРОСТЬ: {result['avg']:.0f}ms avg, {result['p99']:.0f}ms p99")
    else:
        print("\n❌ Стресс-тест не удался!")

if __name__ == "__main__":
    main()