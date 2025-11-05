import requests
import time
import statistics
import json
import uuid
import hashlib
import secrets
from datetime import datetime

BASE_URL = "http://localhost:8000"

def generate_realistic_token(file_path="test.txt"):
    """Генерируем более реалистичный токен на основе анализа кода"""
    # Пробуем разные подходы к генерации токена
    timestamp = str(int(time.time()))
    simple_token = f"{timestamp}:{hashlib.md5(f'{file_path}:{timestamp}'.encode()).hexdigest()}"
    return simple_token

def test_real_attachment_get_endpoint():
    """Тестирование реального /signed/chat/attachments GET эндпоинта"""
    print("🔥 ТЕСТИРОВАНИЕ РЕАЛЬНОГО /signed/chat/attachments (GET) ЭНДПОИНТА")
    print("=" * 65)

    # Тестовые данные
    test_token = generate_realistic_token("test.txt")
    test_params = {
        "token": test_token,
        "file_path": "test.txt"
    }

    print(f"📝 Тестовые параметры: {test_params}")

    # Warmup запросы
    print("🔄 Прогрев (10 запросов)...")
    warmup_times = []
    warmup_status = {}
    response_samples = []

    for i in range(10):
        try:
            start = time.time()
            response = requests.get(f"{BASE_URL}/signed/chat/attachments",
                                  params=test_params,
                                  timeout=15)
            end = time.time()

            response_time = (end - start) * 1000
            warmup_times.append(response_time)

            status = response.status_code
            warmup_status[status] = warmup_status.get(status, 0) + 1

            print(f"  {i+1}/10: {status} - {response_time:.1f}ms")

            # Показываем ответ для анализа
            if i <= 2:  # Только первые 3 ответа
                try:
                    data = response.json()
                    error_detail = data.get('detail', 'No detail')
                    response_samples.append(error_detail)
                    print(f"    📝 Ответ: {error_detail[:80]}")
                except:
                    response_samples.append(response.text[:50])
                    print(f"    📝 Raw: {response.text[:50]}")

        except Exception as e:
            print(f"  {i+1}/10: ERROR - {str(e)[:50]}")

    if not warmup_times:
        print("❌ Warmup не удался")
        return None

    print(f"✅ Прогрев завершен. Среднее: {statistics.mean(warmup_times):.1f}ms")
    print(f"📊 Статусы warmup: {dict(warmup_status)}")
    if response_samples:
        print(f"📝 Примеры ответов: {response_samples[:2]}")

    # Нагрузочный тест
    print("\n🚀 Нагрузочный тест (50 запросов)...")
    response_times = []
    errors = 0
    timeouts = 0
    success_200 = 0
    client_errors = 0
    server_errors = 0
    status_codes = {}

    for i in range(50):
        try:
            # Генерируем новый токен для каждого запроса
            test_token = generate_realistic_token(f"test_file_{i}.txt")
            test_params = {"token": test_token, "file_path": f"test_file_{i}.txt"}

            start = time.time()
            response = requests.get(f"{BASE_URL}/signed/chat/attachments",
                                  params=test_params,
                                  timeout=15)
            end = time.time()

            response_time = (end - start) * 1000
            response_times.append(response_time)

            status = response.status_code
            status_codes[status] = status_codes.get(status, 0) + 1

            if status == 200:
                success_200 += 1
            elif status >= 500:
                server_errors += 1
                errors += 1
            elif status >= 400:
                client_errors += 1
                errors += 1

            if i % 10 == 0 or i == 49:
                print(f"  {i+1}/50: {status} - {response_time:.1f}ms")

        except requests.exceptions.Timeout:
            errors += 1
            timeouts += 1
            print(f"  {i+1}/50: TIMEOUT")
        except Exception as e:
            errors += 1
            print(f"  {i+1}/50: ERROR - {str(e)[:50]}")

    # Статистика
    if response_times:
        avg = statistics.mean(response_times)
        median = statistics.median(response_times)
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        p99 = sorted(response_times)[int(len(response_times) * 0.99)]
        min_time = min(response_times)
        max_time = max(response_times)
        error_rate = (errors / 50) * 100
        success_rate = (success_200 / 50) * 100

        print(f"\n📊 РЕАЛЬНАЯ СТАТИСТИКА /signed/chat/attachments (GET):")
        print(f"   ⏱️  avg/median/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽  min/max: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ✅  200 ответы: {success_200}/50 ({success_rate:.1f}%)")
        print(f"   ❌  ошибки: {errors}/50 ({error_rate:.1f}%)")
        print(f"   🏥  5xx ошибки: {server_errors}")
        print(f"   ⚠️  4xx ошибки: {client_errors}")
        print(f"   ⏰  таймауты: {timeouts}")
        print(f"   📋 статусы: {dict(status_codes)}")

        return {
            'avg': avg,
            'median': median,
            'p95': p95,
            'p99': p99,
            'min': min_time,
            'max': max_time,
            'error_rate': error_rate,
            'success_rate': success_rate,
            'errors': errors,
            'timeouts': timeouts,
            'success_200': success_200,
            'server_errors': server_errors,
            'client_errors': client_errors,
            'status_codes': status_codes
        }
    else:
        print("❌ Все запросы завершились с ошибками!")
        return None

def test_root_endpoint():
    """Тестирование корневого эндпоинта как контроля"""
    print("\n🔥 ТЕСТИРОВАНИЕ КОНТРОЛЬНОГО ЭНДПОИНТА /")
    print("=" * 40)

    print("🔄 Прогрев (5 запросов)...")
    warmup_times = []

    for i in range(5):
        try:
            start = time.time()
            response = requests.get(f"{BASE_URL}/", timeout=10)
            end = time.time()
            warmup_times.append((end - start) * 1000)
            print(f"  {i+1}/5: {response.status_code} - {(end-start)*1000:.1f}ms")
        except Exception as e:
            print(f"  {i+1}/5: ERROR - {str(e)[:30]}")

    print("🚀 Нагрузочный тест (25 запросов)...")
    response_times = []
    errors = 0

    for i in range(25):
        try:
            start = time.time()
            response = requests.get(f"{BASE_URL}/", timeout=10)
            end = time.time()
            response_time = (end - start) * 1000
            response_times.append(response_time)

            if response.status_code != 200:
                errors += 1

            if i % 5 == 0:
                print(f"  {i+1}/25: {response.status_code} - {response_time:.1f}ms")
        except Exception as e:
            errors += 1
            print(f"  {i+1}/25: ERROR")

    if response_times:
        avg = statistics.mean(response_times)
        median = statistics.median(response_times)
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        p99 = sorted(response_times)[int(len(response_times) * 0.99)]
        min_time = min(response_times)
        max_time = max(response_times)
        error_rate = (errors / 25) * 100

        print(f"\n📊 СТАТИСТИКА КОНТРОЛЯ /:")
        print(f"   ⏱️  avg/median/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽  min/max: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ✅  успех: {25-errors}/25 ({100-error_rate:.1f}%)")
        print(f"   ❌  ошибки: {errors}/25 ({error_rate:.1f}%)")

        return {
            'avg': avg, 'median': median, 'p95': p95, 'p99': p99,
            'min': min_time, 'max': max_time, 'error_rate': error_rate
        }
    return None

def main():
    print("🚀 НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ С РЕАЛЬНОЙ БИЗНЕС-ЛОГИКОЙ (GET)")
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 75)

    # Тестируем основной эндпоинт
    result1 = test_real_attachment_get_endpoint()

    # Тестируем контрольный эндпоинт
    result2 = test_root_endpoint()

    # Итоговая сводка
    print("\n" + "=" * 75)
    print("🎯 КРАТКАЯ СВОДКА:")

    if result1:
        print(f"ENDPOINT /signed/chat/attachments | {result1['avg']:.0f}/{result1['median']:.0f}/{result1['p95']:.0f}/{result1['p99']:.0f} | {result1['min']:.0f}/{result1['max']:.0f} | {result1['error_rate']:.1f}% | {result1['success_200']}/50 200-ответов")
    else:
        print("ENDPOINT /signed/chat/attachments | FAILED")

    if result2:
        print(f"ENDPOINT / | {result2['avg']:.0f}/{result2['median']:.0f}/{result2['p95']:.0f}/{result2['p99']:.0f} | {result2['min']:.0f}/{result2['max']:.0f} | {result2['error_rate']:.1f}% | КОНТРОЛЬ")
    else:
        print("ENDPOINT / | FAILED")

if __name__ == "__main__":
    main()