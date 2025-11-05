import requests
import time
import statistics
import json
import uuid
import secrets
from datetime import datetime

BASE_URL = "http://localhost:8000"

def get_session_token():
    """Получаем сессию для аутентификации"""
    try:
        session = requests.Session()
        
        # Получаем главную страницу для создания сессии
        response = session.get(f"{BASE_URL}/")
        if response.status_code == 200:
            # Проверяем куки
            cookies = session.cookies.get_dict()
            if cookies:
                print(f"✅ Получены куки: {list(cookies.keys())}")
                return session
            else:
                print("⚠️ Куки не найдены, пробуем создать сессию вручную")
                # Создаем сессию вручную
                session_data = {
                    "thread_id": str(uuid.uuid4()),
                    "user_agent": "load_test_client"
                }
                response = session.post(f"{BASE_URL}/session/create", json=session_data)
                if response.status_code == 200:
                    print(f"✅ Сессия создана: {response.status_code}")
                    return session
    except Exception as e:
        print(f"❌ Ошибка создания сессии: {e}")
    return None

def test_endpoint_with_auth(session, endpoint, data=None, method="POST", warmup_requests=10, load_requests=50):
    """Тестирование эндпоинта с аутентификацией"""
    print(f"\n🔥 Тестируем эндпоинт: {endpoint}")
    print("=" * 50)
    
    # Warmup запросы
    print(f"🔄 Warmup ({warmup_requests} запросов)...")
    warmup_times = []
    warmup_status_codes = {}
    
    for i in range(warmup_requests):
        try:
            start = time.time()
            if method == "POST" and data:
                response = session.post(f"{BASE_URL}{endpoint}", json=data, timeout=10)
            else:
                response = session.get(f"{BASE_URL}{endpoint}", timeout=10)
            end = time.time()
            
            response_time = (end - start) * 1000
            warmup_times.append(response_time)
            
            status = response.status_code
            warmup_status_codes[status] = warmup_status_codes.get(status, 0) + 1
            
            if i % 3 == 0:
                print(f"  Warmup {i+1}/{warmup_requests}: {status} - {response_time:.1f}ms")
                
        except Exception as e:
            print(f"  Warmup {i+1}: ERROR - {str(e)}")
    
    print(f"✅ Warmup завершен. Среднее время: {statistics.mean(warmup_times):.1f}ms")
    print(f"📊 Статусы warmup: {dict(warmup_status_codes)}")
    
    # Нагрузочные запросы
    print(f"\n🚀 Нагрузочный тест ({load_requests} запросов)...")
    response_times = []
    errors = 0
    timeouts = 0
    server_errors = 0
    client_errors = 0
    success_requests = 0
    status_codes = {}
    
    for i in range(load_requests):
        try:
            start = time.time()
            if method == "POST" and data:
                response = session.post(f"{BASE_URL}{endpoint}", json=data, timeout=10)
            else:
                response = session.get(f"{BASE_URL}{endpoint}", timeout=10)
            end = time.time()
            
            response_time = (end - start) * 1000
            response_times.append(response_time)
            
            status = response.status_code
            status_codes[status] = status_codes.get(status, 0) + 1
            
            # Подсчет ошибок
            if status >= 500:
                server_errors += 1
            elif status >= 400:
                client_errors += 1
            elif status == 200:
                success_requests += 1
            elif response_time > 10000:  # 10 секунд таймаут
                timeouts += 1
                
            if i % 10 == 0 or i == load_requests - 1:
                print(f"  Request {i+1}/{load_requests}: {status} - {response_time:.1f}ms")
                
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
        success_rate = (success_requests / load_requests) * 100
        
        print(f"\n📊 СТАТИСТИКА для {endpoint}:")
        print(f"   ⏱️  Среднее/медиана/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽 Мин/Макс: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ✅ Успешно: {success_requests}/{load_requests} ({success_rate:.1f}%)")
        print(f"   ❌ Ошибки: {errors}/{load_requests} ({error_rate:.1f}%)")
        print(f"   🏥 5xx ошибки: {server_errors}")
        print(f"   ⚠️  4xx ошибки: {client_errors}")
        print(f"   ⏰ Таймауты: {timeouts}")
        print(f"   📋 Статусы: {dict(status_codes)}")
        
        return {
            'endpoint': endpoint,
            'avg': avg,
            'median': median, 
            'p95': p95,
            'p99': p99,
            'min': min_time,
            'max': max_time,
            'success_rate': success_rate,
            'error_rate': error_rate,
            'errors': errors,
            'server_errors': server_errors,
            'client_errors': client_errors,
            'timeouts': timeouts,
            'success_requests': success_requests,
            'status_codes': status_codes
        }
    else:
        print(f"\n❌ Все запросы завершились с ошибками!")
        return None

def main():
    print("🚀 НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ БЭКЕНДА С АУТЕНТИФИКАЦИЕЙ")
    print(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Получаем сессию
    session = get_session_token()
    if not session:
        print("❌ Не удалось получить сессию. Пробуем без аутентификации.")
        session = requests.Session()
    
    # Тестовые данные
    chat_data = {
        "message": "Test message for advanced load testing with authentication",
        "thread_id": f"test-thread-{uuid.uuid4().hex[:8]}"
    }
    
    results = []
    
    # Тест 1: /chat (POST) с аутентификацией
    result1 = test_endpoint_with_auth(session, "/chat", chat_data, "POST", 10, 50)
    if result1:
        results.append(result1)
    
    # Тест 2: Простой GET запрос к корню
    result2 = test_endpoint_with_auth(session, "/", None, "GET", 5, 50)
    if result2:
        results.append(result2)
    
    # Итоговая таблица
    print("\n" + "=" * 70)
    print("📋 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print("=" * 70)
    print(f"{'ЭНДПОИНТ':<30} | {'AVG/MED/P95/P99':<20} | {'MIN/MAX':<12} | {'УСПЕХ':<8} | {'ОШИБКИ':<8}")
    print("-" * 90)
    
    for result in results:
        endpoint_short = result['endpoint'].replace('/chat', '/CHAT').replace('/', '/ROOT')[:25]
        perf_str = f"{result['avg']:.0f}/{result['median']:.0f}/{result['p95']:.0f}/{result['p99']:.0f}"
        perf_str = perf_str[:18]
        minmax_str = f"{result['min']:.0f}/{result['max']:.0f}"
        minmax_str = minmax_str[:10]
        success_str = f"{result['success_rate']:.0f}%"
        errors_str = f"{result['error_rate']:.1f}%"
        
        print(f"{endpoint_short:<30} | {perf_str:<20} | {minmax_str:<12} | {success_str:<8} | {errors_str:<8}")
    
    print("\n🎯 КРАТКАЯ СВОДКА:")
    for result in results:
        endpoint_name = result['endpoint'].replace('/chat', 'CHAT').replace('/', 'ROOT')
        print(f"ENDPOINT {endpoint_name} | {result['avg']:.0f}/{result['median']:.0f}/{result['p95']:.0f}/{result['p99']:.0f} | {result['min']:.0f}/{result['max']:.0f} | {result['error_rate']:.1f}%")

if __name__ == "__main__":
    main()
