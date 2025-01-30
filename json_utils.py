# json_utils.py

import json
import asyncio
from typing import List, Dict, Any
import os

class JSONDataStore:
    """
    Класс для асинхронного чтения и записи данных в JSON-файлы.
    Обеспечивает безопасность при одновременном доступе.
    """

    def __init__(self, filepath: str):
        """
        Инициализирует объект JSONDataStore.

        :param filepath: Путь к JSON-файлу.
        """
        self.filepath = filepath
        self.lock = asyncio.Lock()
        # Создаём файл, если он не существует
        if not os.path.exists(self.filepath):
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump([], f)

    async def read_data(self) -> List[Dict[str, Any]]:
        """
        Асинхронно читает данные из JSON-файла.

        :return: Список словарей, представляющих данные в файле.
        """
        async with self.lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._read_file)

    def _read_file(self) -> List[Dict[str, Any]]:
        """
        Синхронно читает данные из JSON-файла.

        :return: Список словарей, представляющих данные в файле.
        """
        with open(self.filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                else:
                    # Если данные не являются списком, возвращаем пустой список
                    return []
            except json.JSONDecodeError:
                # Если файл пуст или содержит некорректный JSON, возвращаем пустой список
                return []

    async def write_data(self, data: List[Dict[str, Any]]) -> None:
        """
        Асинхронно записывает данные в JSON-файл.

        :param data: Список словарей, которые необходимо записать в файл.
        """
        async with self.lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_file, data)

    def _write_file(self, data: List[Dict[str, Any]]) -> None:
        """
        Синхронно записывает данные в JSON-файл.

        :param data: Список словарей, которые необходимо записать в файл.
        """
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
