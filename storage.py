import json
import aiofiles
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import asyncio

class CityData(BaseModel):
    name: str
    latitude: float
    longitude: float
    last_updated: Optional[datetime] = None
    forecast: Dict[str, Any] = {}

class UserData(BaseModel):
    user_id: str
    username: str
    cities: Dict[str, CityData] = {}
    created_at: datetime = datetime.now()

class WeatherStorage:
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.users: Dict[str, UserData] = {}  # user_id -> UserData
        self._load_lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()
    
    async def load_data(self):
        # Загрузка данных из файла
        async with self._load_lock:
            try:
                async with aiofiles.open(self.data_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    if content:
                        data = json.loads(content)
                        
                        # Восстанавливаем данные пользователей
                        for user_id_str, user_data in data.get('users', {}).items():
                            # Конвертируем строки datetime обратно
                            if user_data.get('created_at'):
                                user_data['created_at'] = datetime.fromisoformat(user_data['created_at'])
                            
                            # Восстанавливаем города пользователя
                            cities_dict = {}
                            for city_name, city_data in user_data.get('cities', {}).items():
                                if city_data.get('last_updated'):
                                    city_data['last_updated'] = datetime.fromisoformat(city_data['last_updated'])
                                cities_dict[city_name] = CityData(**city_data)
                            
                            user_data['cities'] = cities_dict
                            self.users[user_id_str] = UserData(**user_data)
            except FileNotFoundError:
                # Файл не существует, начнем с пустого хранилища
                pass
            except json.JSONDecodeError as e:
                print(f"Ошибка при чтении файла данных: {e}")
                # Файл поврежден, начнем с пустого хранилища
                pass
    
    async def save_data(self):
        # Сохранение данных в файл
        async with self._save_lock:
            data_to_save = {
                'users': {}
            }
            
            for user_id, user_data in self.users.items():
                user_dict = user_data.dict()
                # Конвертируем datetime в строку
                user_dict['created_at'] = user_dict['created_at'].isoformat()
                
                # Конвертируем города
                cities_dict = {}
                for city_name, city_data in user_data.cities.items():
                    city_dict = city_data.dict()
                    if city_dict['last_updated']:
                        city_dict['last_updated'] = city_dict['last_updated'].isoformat()
                    cities_dict[city_name] = city_dict
                
                user_dict['cities'] = cities_dict
                data_to_save['users'][user_id] = user_dict
            
            async with aiofiles.open(self.data_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data_to_save, ensure_ascii=False, indent=2))
    
    async def create_user(self, username: str) -> str:
        # Создание нового пользователя
        import uuid
        user_id = str(uuid.uuid4())
        
        user_data = UserData(
            user_id=user_id,
            username=username,
            cities={}
        )
        
        self.users[user_id] = user_data
        await self.save_data()
        return user_id
    
    async def get_user(self, user_id: str) -> Optional[UserData]:
        # Получение данных пользователя
        return self.users.get(user_id)
    
    async def get_user_by_username(self, username: str) -> Optional[UserData]:
        # Поиск пользователя по имени
        for user in self.users.values():
            if user.username == username:
                return user
        return None
    
    async def add_city_to_user(self, user_id: str, name: str, latitude: float, longitude: float) -> bool:
        # Добавление города пользователю
        user = await self.get_user(user_id)
        if not user:
            return False
        
        city = CityData(name=name, latitude=latitude, longitude=longitude)
        user.cities[name] = city
        await self.save_data()
        return True
    
    async def get_user_cities(self, user_id: str) -> List[str]:
        # Получение списка городов пользователя
        user = await self.get_user(user_id)
        if not user:
            return []
        return list(user.cities.keys())
    
    async def get_user_city(self, user_id: str, city_name: str) -> Optional[CityData]:
        # Получение города пользователя
        user = await self.get_user(user_id)
        if not user:
            return None
        return user.cities.get(city_name)
    
    async def update_city_forecast(self, user_id: str, city_name: str, forecast: Dict[str, Any]):
        # Обновление прогноза для города пользователя
        user = await self.get_user(user_id)
        if not user or city_name not in user.cities:
            return
        
        user.cities[city_name].forecast = forecast
        user.cities[city_name].last_updated = datetime.now()
        await self.save_data()
    
    async def city_needs_update(self, user_id: str, city_name: str, update_interval: int) -> bool:
        # Проверка необходимости обновления прогноза для города пользователя
        user = await self.get_user(user_id)
        if not user or city_name not in user.cities:
            return False
        
        city = user.cities[city_name]
        if not city.last_updated:
            return True
        
        time_since_update = datetime.now() - city.last_updated
        return time_since_update.total_seconds() > update_interval
    
    async def get_all_users(self) -> List[UserData]:
        # Получение списка всех пользователей
        return list(self.users.values())