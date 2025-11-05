import requests
import time
import statistics
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint, data=None, method="POST", warmup_requests=10, load_requests=50):
    """Тестирование эндпоинта с нагрузкой"""
    print(f"\n🔥 Тестируем эндпоинт: {endpoint}")
    print("=" * 50)
    
    # Warmup запросы
    print(f"🔄 Warmup ({warmup_requests} запросов)...")
    warmup_times = []
    for i in range(warmup_requests):
        try:
            start = time.time()
            if method == "POST" and data:
                response = requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=5)
            else:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
            end = time.time()
            warmup_times.append((end - start) * 1000)  # ms
            if i % 3 == 0:
                print(f"  Warmup {i+1}/{warmup_requests}: {response.status_code} - {(end-start)*1000:.1f}ms")
        except Exception as e:
            print(f"  Warmup {i+1}: ERROR - {str(e)}")
    
    print(f"✅ Warmup завершен. Среднее время: {statistics.mean(warmup_times):.1f}ms")
    
    # Нагрузочные запросы
    print(f"\n🚀 Нагрузочный тест ({load_requests} запросов)...")
    response_times = []
    errors = 0
    timeouts = 0
    server_errors = 0
    
    for i in range(load_requests):
        try:
            start = time.time()
            if method == "POST" and data:
                response = requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=5)
            else:
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
            end = time.time()
            
            response_time = (end - start) * 1000
            response_times.append(response_time)
            
            # Подсчет ошибок
            if response.status_code >= 500:
                server_errors += 1
            elif response_time > 5000:  # timeout
                timeouts += 1
                
            if i % 10 == 0 or i == load_requests - 1:
                print(f"  Request {i+1}/{load_requests}: {response.status_code} - {response_time:.1f}ms")
                
        except requests.exceptions.Timeout:
            errors += 1
            timeouts += 1
            print(f"  Request {i+1}: TIMEOUT")
        except Exception as e:
            errors += 1
            print(f"  Request {i+1}: ERROR - {str(e)}")
    
    # Статистика
    if response_times:
        avg = statistics.mean(response_times)
        median = statistics.median(response_times)
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        p99 = sorted(response_times)[int(len(response_times) * 0.99)]
        min_time = min(response_times)
        max_time = max(response_times)
        error_rate = (errors / load_requests) * 100
        
        print(f"\n📊 СТАТИСТИКА для {endpoint}:")
        print(f"   ⏱️  Среднее/медиана/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽 Мин/Макс: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ❌ Ошибки: {errors}/{load_requests} ({error_rate:.1f}%)")
        print(f"   🏥 5xx ошибки: {server_errors}")
        print(f"   ⏰ Таймауты: {timeouts}")
        
        return {
            'endpoint': endpoint,
            'avg': avg,
            'median': median, 
            'p95': p95,
            'p99': p99,
            'min': min_time,
            'max': max_time,
            'error_rate': error_rate,
            'errors': errors,
            'server_errors': server_errors,
            'timeouts': timeouts
        }
    else:
        print(f"\n❌ Все запросы завершились с ошибками!")
        return None

def main():
    print("🚀 НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ БЭКЕНДА")
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Тестовые данные
    chat_data = {
        "message": "Test message for load testing",
        "thread_id": "test-thread-load"
    }
    
    attachment_data = {
        "file_path": "test.txt",
        "file_name": "test.txt"
    }
    
    results = []
    
    # Тест 1: /chat (POST)
    result1 = test_endpoint("/chat", chat_data, "POST", 10, 50)
    if result1:
        results.append(result1)
    
    # Тест 2: /signed/chat/attachments (POST)
    result2 = test_endpoint("/signed/chat/attachments", attachment_data, "POST", 10, 50)
    if result2:
        results.append(result2)
    
    # Тест 3: Простой GET запрос (корень)
    result3 = test_endpoint("/", None, "GET", 5, 25)
    if result3:
        results.append(result3)
    
    # Итоговая таблица
    print("\n" + "=" * 60)
    print("📋 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 60)
    print(f"{'ЭНДПОИНТ':<30} | {'AVG/MED/P95/P99':<20} | {'MIN/MAX':<12} | {'ОШИБКИ':<10}")
    print("-" * 80)
    
    for result in results:
        endpoint_short = result['endpoint'].replace('/chat', '/CHAT').replace('/signed/chat/attachments', '/ATTACH').replace('/', '/ROOT')[:25]
        perf_str = f"{result['avg']:.0f}/{result['median']:.0f}/{result['p95']:.0f}/{result['p99']:.0f}"
        perf_str = perf_str[:18]
        minmax_str = f"{result['min']:.0f}/{result['max']:.0f}"
        errors_str = f"{result['error_rate']:.1f}%"
        
        print(f"{endpoint_short:<30} | {perf_str:<20} | {minmax_str:<12} | {errors_str:<10}")

if __name__ == "__main__":
    main()
