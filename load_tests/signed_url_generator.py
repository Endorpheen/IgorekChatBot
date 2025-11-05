import requests
import hashlib
import time
import json

BASE_URL = "http://localhost:8000"

def create_test_file_and_get_signed_url():
    """Создаем тестовый файл и получаем валидный signed URL"""
    try:
        # Сначала попробуем создать файл через эндпоинт загрузки
        test_file_content = "A" * 1500  # ~1.5KB файл

        # Создаем файл
        create_data = {
            "file_name": "test_load_file.txt",
            "file_size": len(test_file_content)
        }

        response = requests.post(f"{BASE_URL}/signed/upload", json=create_data, timeout=10)

        if response.status_code == 200:
            data = response.json()
            signed_url = data.get("signed_url")
            file_id = data.get("file_id")

            print(f"✅ Получен валидный signed URL:")
            print(f"   📁 File ID: {file_id}")
            print(f"   🔗 Signed URL: {signed_url[:100]}..." if len(signed_url) > 100 else f"   🔗 Signed URL: {signed_url}")

            return signed_url, file_id
        else:
            print(f"❌ Ошибка создания файла: {response.status_code}")
            print(f"   📝 Ответ: {response.text}")
            return None, None

    except Exception as e:
        print(f"❌ Исключение при создании signed URL: {e}")
        return None, None

def test_signed_url_access(signed_url):
    """Тестируем доступ по signed URL"""
    try:
        response = requests.get(signed_url, timeout=10)
        return response.status_code == 200
    except:
        return False

def main():
    print("🔗 ГЕНЕРАТОР ВАЛИДНЫХ SIGNED URL")
    print("=" * 50)

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
    signed_url, file_id = create_test_file_and_get_signed_url()

    if signed_url:
        # Тестируем доступ
        print(f"\n🧪 Тестируем доступ к signed URL...")
        if test_signed_url_access(signed_url):
            print(f"✅ Signed URL работает - возвращает 200!")
            print(f"\n🎯 ГОТОВО К СТРЕСС-ТЕСТУ:")
            print(f"   URL: {signed_url}")
            print(f"   File ID: {file_id}")
        else:
            print(f"❌ Signed URL не работает")
    else:
        print(f"\n❌ Не удалось создать валидный signed URL")

        # Альтернативный подход - исследуем доступные эндпоинты
        print(f"\n🔍 Ищем альтернативные эндпоинты...")
        try:
            # Пробуем разные эндпоинты для создания signed URLs
            endpoints = [
                "/signed/create",
                "/signed/generate",
                "/api/signed/create",
                "/upload/signed",
                "/files/signed"
            ]

            for endpoint in endpoints:
                try:
                    response = requests.post(f"{BASE_URL}{endpoint}",
                                          json={"file_name": "test.txt"},
                                          timeout=5)
                    if response.status_code == 200:
                        print(f"✅ Найден работающий эндпоинт: {endpoint}")
                        print(f"   Ответ: {response.json()}")
                        break
                except:
                    continue

        except Exception as e:
            print(f"❌ Поиск альтернативных эндпоинтов не удался: {e}")

if __name__ == "__main__":
    main()