# Weather Service API

Асинхронный HTTP-сервер для предоставления информации о погоде с использованием Open-Meteo API.

## Установка
Для основного скрипта:
pip install -r requirements.txt

Для тестов:
pip install -r requirements-test.txt

## Запуск сервера
python script.py

## Структура проекта
weather_service/
├── script.py              # Основной файл сервера FastAPI
├── storage.py             # Модуль для хранения данных пользователей и городов
├── config.py              # Конфигурация приложения
├── test_weather_api.py    # Юнит-тесты для API
├── weather_data.json      # Файл для хранения данных (создается автоматически)
├── requirements.txt       # Зависимости проекта
├── requirements-test.txt  # Зависимости для тестов
└── README.md              # Документация

1. Текущая погода по координатам
Параметры:
latitude (float, обязательный) - широта (-90 до 90)
longitude (float, обязательный) - долгота (-180 до 180)

Пример запроса:
curl "http://127.0.0.1:8000/weather/current?latitude=55.7558&longitude=37.6176"

2. Регистрация пользователя
Пример запроса:
curl -X POST "http://127.0.0.1:8000/users/register?username=Ivan"

3. Добавление города пользователю
Параметры пути:
user_id (string, обязательный) - ID пользователя, полученный при регистрации
Параметры запроса:
name (string, обязательный) - название города
latitude (float, обязательный) - широта города
longitude (float, обязательный) - долгота города

Пример запроса:
curl -X POST "http://127.0.0.1:8000/users/550e8400-e29b-41d4-a716-446655440000/cities/add?name=Moscow&latitude=55.7558&longitude=37.6176"

4. Список городов пользователя
GET /users/{user_id}/cities/list
Возвращает список городов, которые добавлены пользователем для отслеживания погоды.
Параметры пути:
user_id (string, обязательный) - ID пользователя

Пример запроса:
curl "http://127.0.0.1:8000/users/550e8400-e29b-41d4-a716-446655440000/cities/list"

5. Прогноз погоды для города пользователя
GET /users/{user_id}/weather/forecast
Возвращает прогноз погоды для указанного города пользователя. Можно указать конкретное время и выбрать, какие параметры погоды получать.

Параметры пути:
user_id (string, обязательный) - ID пользователя

Параметры запроса:
city (string, обязательный) - название города
time (string, опциональный) - время в формате ISO (например: "2024-01-15T14:00:00"). Если не указано, используется текущее время
params (string, опциональный) - параметры погоды через запятую

Доступные параметры погоды:
temperature - температура в °C
humidity - влажность в %
wind_speed - скорость ветра в км/ч
precipitation - осадки в мм

Примеры запросов:
Все параметры для текущего времени:

curl "http://127.0.0.1:8000/users/550e8400-e29b-41d4-a716-446655440000/weather/forecast?city=Moscow"
Только температура и влажность на 14:00:

curl "http://127.0.0.1:8000/users/550e8400-e29b-41d4-a716-446655440000/weather/forecast?city=Moscow&time=2026-01-22T14:00:00&params=temperature,humidity"
Только скорость ветра:

curl "http://127.0.0.1:8000/users/550e8400-e29b-41d4-a716-446655440000/weather/forecast?city=Moscow&params=wind_speed"

## Запуск тестов:
1. Простой запуск
python -m pytest test_weather_api.py -v
2. С покрытием
python -m pytest test_weather_api.py -v --cov=script --cov-report=term-missing