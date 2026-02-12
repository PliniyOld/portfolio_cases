import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Настройки сервера
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    
    # Настройки Open-Meteo API
    OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
    
    # Настройки хранения
    DATA_FILE = os.getenv("DATA_FILE", "weather_data.json")
    UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", 900))  # 15 минут в секундах
    
    # Параметры погоды по умолчанию
    DEFAULT_PARAMS = ["temperature", "windspeed", "pressure", "humidity", "precipitation"]

config = Config()