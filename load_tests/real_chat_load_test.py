import requests
import time
import statistics
import json
import uuid

BASE_URL = "http://localhost:8000"

def test_real_chat_endpoint():
    """Тестирование реального /chat эндпоинта"""
    print("🔥 ТЕСТИРОВАНИЕ РЕАЛЬНОГО /chat ЭНДПОИНТА")
    print("=" * 50)
    
    # Минимальные тестовые данные
    test_data = {
        "message": "hi",
        "thread_id": str(uuid.uuid4())[:8]  # короткий ID
    }
    
    print(f"📝 Тестовые данные: {test_data}")
    
    # Warmup запросы
    print("🔄 Прогрев (10 запросов)...")
    warmup_times = []
    
    for i in range(10):
        try:
            start = time.time()
            response = requests.post(f"{BASE_URL}/chat", json=test_data, timeout=15)
            end = time.time()
            
            response_time = (end - start) * 1000
            warmup_times.append(response_time)
            
            print(f"  {i+1}/10: {response.status_code} - {response_time:.1f}ms")
            
            # Проверяем, получил ли мы реальный ответ
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"    📝 Ответ: {data.get('response', 'N/A')[:50]}")
                except:
                    print(f"    📝 Raw response: {response.text[:100]}")
                    
        except Exception as e:
            print(f"  {i+1}/10: ERROR - {str(e)[:50]}")
    
    if not warmup_times:
        print("❌ Warmup не удался")
        return None
    
    print(f"✅ Прогрев завершен. Среднее: {statistics.mean(warmup_times):.1f}ms")
    
    # Нагрузочный тест
    print("\n🚀 Нагрузочный тест (50 запросов)...")
    response_times = []
    errors = 0
    timeouts = 0
    success_200 = 0
    responses = []
    
    for i in range(50):
        try:
            start = time.time()
            response = requests.post(f"{BASE_URL}/chat", json=test_data, timeout=15)
            end = time.time()
            
            response_time = (end - start) * 1000
            response_times.append(response_time)
            
            status = response.status_code
            if status == 200:
                success_200 += 1
                try:
                    data = response.json()
                    responses.append(data)
                    response_length = len(str(data))
                    if i % 10 == 0:
                        print(f"  {i+1}/50: {status} - {response_time:.1f}ms - {response_length} chars")
                except:
                    print(f"  {i+1}/50: {status} - {response_time:.1f} - invalid json")
            else:
                errors += 1
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
        
        print(f"\n📊 РЕАЛЬНАЯ СТАТИСТИКА /chat:")
        print(f"   ⏱️  avg/median/p95/p99: {avg:.1f}/{median:.1f}/{p95:.1f}/{p99:.1f} ms")
        print(f"   🔽  min/max: {min_time:.1f}/{max_time:.1f} ms")
        print(f"   ✅  200 ответы: {success_200}/50 ({success_rate:.1f}%)")
        print(f"   ❌  ошибки: {errors}/50 ({error_rate:.1f}%)")
        print(f"   ⏰  таймауты: {timeouts}")
        
        # Анализ ответов
        if responses:
            response_lengths = [len(str(r)) for r in responses]
            avg_response_len = statistics.mean(response_lengths)
            print(f"   📊 средний ответ: {avg_response_len:.0f} символов")
        
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
            'success_200': success_200
        }
    else:
        print("❌ Все запросы завершились с ошибками!")
        return None

def main():
    result = test_real_chat_endpoint()
    
    if result:
        print("\n" + "=" * 60)
        print("🎯 КРАТКАЯ СВОДКА:")
        print(f"ENDPOINT /chat | {result['avg']:.0f}/{result['median']:.0f}/{result['p95']:.0f}/{result['p99']:.0f} | {result['min']:.0f}/{result['max']:.0f} | {result['error_rate']:.1f}%")
    else:
        print("\n❌ Тест не удался")

if __name__ == "__main__":
    main()
