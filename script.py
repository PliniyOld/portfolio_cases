from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import httpx
from datetime import datetime, timedelta
import asyncio
from typing import List, Optional
import uvicorn

from config import config
from storage import WeatherStorage

# Глобальные переменные
storage = None
http_client = None
update_task = None

def filter_weather_params(forecast: dict, params: Optional[str]) -> dict:
    # Фильтрация параметров погоды
    if params:
        requested_params = [p.strip().lower() for p in params.split(",")]
        filtered_forecast = {"time": forecast["time"]}
        
        for param in requested_params:
            if param in ["temperature", "humidity", "wind_speed", "precipitation"]:
                filtered_forecast[param] = forecast.get(param)
        
        return filtered_forecast
    else:
        # Возвращаем все параметры по умолчанию
        return {
            "time": forecast["time"],
            "temperature": forecast.get("temperature"),
            "humidity": forecast.get("humidity"),
            "wind_speed": forecast.get("wind_speed"),
            "precipitation": forecast.get("precipitation")
        }

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Контекстный менеджер для управления жизненным циклом приложения
    global storage, http_client, update_task
    
    # Startup
    print("Starting up...")
    storage = WeatherStorage(config.DATA_FILE)
    http_client = httpx.AsyncClient(timeout=30.0)
    await storage.load_data()
    
    # Запускаем периодическое обновление погоды
    update_task = asyncio.create_task(periodic_weather_update())
    
    yield
    
    # Shutdown
    print("Shutting down...")
    if update_task:
        update_task.cancel()
        try:
            await update_task
        except asyncio.CancelledError:
            pass
    
    if http_client:
        await http_client.aclose()

app = FastAPI(
    title="Weather Service API",
    description="API для получения информации о погоде с поддержкой нескольких пользователей",
    version="1.0.0",
    lifespan=lifespan
)

async def fetch_weather(latitude: float, longitude: float) -> dict:
    # Получение текущей погоды из Open-Meteo API
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ["temperature_2m", "wind_speed_10m", "pressure_msl", "relative_humidity_2m", "precipitation"],
        "hourly": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation"],
        "forecast_days": 1,
        "timezone": "auto"
    }
    
    try:
        response = await http_client.get(config.OPEN_METEO_URL, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Ошибка при запросе к погодному API: {str(e)}")

def format_current_weather(weather_data: dict) -> dict:
    # Форматирование данных текущей погоды
    current = weather_data.get("current", {})
    return {
        "temperature": current.get("temperature_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "pressure": current.get("pressure_msl"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "timestamp": datetime.now().isoformat()
    }

def format_hourly_forecast(weather_data: dict, target_time: str) -> dict:
    # Форматирование почасового прогноза для указанного времени
    hourly = weather_data.get("hourly", {})
    times = hourly.get("time", [])
    
    if not times:
        raise HTTPException(status_code=404, detail="Данные прогноза не содержат временных меток")
    
    try:
        # Пробуем разные форматы времени
        try:
            target_datetime = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
        except ValueError:
            # Пробуем другие форматы даты
            for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]:
                try:
                    target_datetime = datetime.strptime(target_time, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Неверный формат времени: {target_time}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка формата времени: {str(e)}")
    
    best_match_index = 0
    min_diff = float('inf')
    
    for i, time_str in enumerate(times):
        try:
            time_dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            diff = abs((time_dt - target_datetime).total_seconds())
            if diff < min_diff:
                min_diff = diff
                best_match_index = i
        except ValueError:
            continue
    
    # Если разница больше 12 часов, считаем что время слишком далеко
    if min_diff > 43200:  # 12 часов в секундах
        raise HTTPException(
            status_code=400, 
            detail=f"Указанное время слишком далеко от доступных данных прогноза. Ближайшее доступное время: {times[best_match_index]}"
        )
    
    return {
        "time": times[best_match_index],
        "temperature": hourly.get("temperature_2m", [])[best_match_index] if hourly.get("temperature_2m") else None,
        "humidity": hourly.get("relative_humidity_2m", [])[best_match_index] if hourly.get("relative_humidity_2m") else None,
        "wind_speed": hourly.get("wind_speed_10m", [])[best_match_index] if hourly.get("wind_speed_10m") else None,
        "precipitation": hourly.get("precipitation", [])[best_match_index] if hourly.get("precipitation") else None
    }

async def periodic_weather_update():
    # Периодическое обновление прогноза для всех городов всех пользователей
    while True:
        try:
            users = await storage.get_all_users()
            for user in users:
                cities = await storage.get_user_cities(user.user_id)
                for city_name in cities:
                    if await storage.city_needs_update(user.user_id, city_name, config.UPDATE_INTERVAL):
                        city_data = await storage.get_user_city(user.user_id, city_name)
                        if city_data:
                            weather_data = await fetch_weather(city_data.latitude, city_data.longitude)
                            await storage.update_city_forecast(user.user_id, city_name, weather_data)
        except Exception as e:
            print(f"Ошибка при обновлении прогноза: {e}")
        
        # Ждем 15 минут до следующего обновления
        await asyncio.sleep(config.UPDATE_INTERVAL)

@app.get("/")
async def root():
    # Корневая страница с документацией API
    return {
        "message": "Weather API",
        "version": "1.0.0",
        "description": "API для получения информации о погоде с поддержкой нескольких пользователей",
        "endpoints": {
            "GET /weather/current": "Текущая погода по координатам",
            "POST /users/register": "Регистрация нового пользователя",
            "POST /users/{user_id}/cities/add": "Добавление города для пользователя",
            "GET /users/{user_id}/cities/list": "Список городов пользователя",
            "GET /users/{user_id}/weather/forecast": "Прогноз погоды для города пользователя",
        }
    }

@app.post("/users/register")
async def register_user(username: str = Query(..., description="Имя пользователя")):
    try:
        # Проверяем, не существует ли уже пользователь с таким именем
        existing_user = await storage.get_user_by_username(username)
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail=f"Пользователь с именем '{username}' уже существует"
            )
        
        user_id = await storage.create_user(username)
        
        return JSONResponse(content={
            "message": f"Пользователь {username} успешно зарегистрирован",
            "username": username,
            "user_id": user_id,
            "created_at": datetime.now().isoformat()
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/weather/current")
async def get_current_weather(
    latitude: float = Query(..., description="Широта"),
    longitude: float = Query(..., description="Долгота")
):
    try:
        weather_data = await fetch_weather(latitude, longitude)
        formatted_weather = format_current_weather(weather_data)
        
        response = {
            "temperature": formatted_weather["temperature"],
            "wind_speed": formatted_weather["wind_speed"],
            "pressure": formatted_weather["pressure"],
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude
            },
            "timestamp": formatted_weather["timestamp"]
        }
        
        return JSONResponse(content=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/users/{user_id}/cities/add")
async def add_city_to_user(
    user_id: str,
    name: str = Query(..., description="Название города"),
    latitude: float = Query(..., description="Широта"),
    longitude: float = Query(..., description="Долгота")
):
    try:
        # Проверяем существование пользователя
        user = await storage.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"Пользователь с ID {user_id} не найден")
        
        # Добавляем город
        success = await storage.add_city_to_user(user_id, name, latitude, longitude)
        if not success:
            raise HTTPException(status_code=500, detail="Не удалось добавить город")
        
        # Немедленно получаем прогноз для нового города
        weather_data = await fetch_weather(latitude, longitude)
        await storage.update_city_forecast(user_id, name, weather_data)
        
        return JSONResponse(content={
            "message": f"Город {name} добавлен для отслеживания погоды пользователем {user.username}",
            "user_id": user_id,
            "username": user.username,
            "city": name,
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/cities/list")
async def list_user_cities(user_id: str):
    # Получение списка городов, для которых доступен прогноз погоды для указанного пользователя
    try:
        # Проверяем существование пользователя
        user = await storage.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"Пользователь с ID {user_id} не найден")
        
        cities = await storage.get_user_cities(user_id)
        
        return JSONResponse(content={
            "user_id": user_id,
            "username": user.username,
            "cities": cities,
            "count": len(cities)
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users/{user_id}/weather/forecast")
async def get_user_weather_forecast(
    user_id: str,
    city: str = Query(..., description="Название города"),
    time: Optional[str] = Query(None, description="Время в формате ISO (например, 2024-01-15T14:00:00). Если не указано, используется текущее время"),
    params: Optional[str] = Query(None, description="Параметры погоды через запятую (temperature,humidity,wind_speed,precipitation)")
):
    try:
        # Проверяем существование пользователя
        user = await storage.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"Пользователь с ID {user_id} не найден")
        
        # Проверяем, есть ли город в списке пользователя
        city_data = await storage.get_user_city(user_id, city)
        if not city_data:
            raise HTTPException(
                status_code=404, 
                detail=f"Город {city} не найден в списке городов пользователя {user.username}"
            )
        
        # Проверяем, нуждается ли прогноз в обновлении
        if await storage.city_needs_update(user_id, city, config.UPDATE_INTERVAL):
            weather_data = await fetch_weather(city_data.latitude, city_data.longitude)
            await storage.update_city_forecast(user_id, city, weather_data)
            forecast_data = weather_data
        else:
            forecast_data = city_data.forecast
        
        if not forecast_data:
            raise HTTPException(status_code=404, detail=f"Прогноз для города {city} не доступен")
        
        # Если время не указано, используем текущее время
        if time is None:
            now = datetime.now()
            current_time = now.replace(minute=0, second=0, microsecond=0).isoformat()
            target_time = current_time
        else:
            target_time = time
        
        # Получаем прогноз для указанного времени
        forecast = format_hourly_forecast(forecast_data, target_time)
        
        # Фильтруем параметры, если указано
        response = filter_weather_params(forecast, params)
        
        response["user_id"] = user_id
        response["username"] = user.username
        response["city"] = city
        response["requested_time"] = target_time
        response["is_current_time"] = time is None
        
        return JSONResponse(content=response)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "script:app",
        host=config.HOST,
        port=config.PORT,
        reload=True
    )