# paginator.py
# ------------

from typing import List, TypeVar, Generic, Callable, Optional

T = TypeVar('T')


class Paginator(Generic[T]):
    """
    Класс для пагинации списков элементов.
    """

    def __init__(self, items: List[T], page_size: int = 5):
        self.items = items
        self.page_size = page_size
        self.total_pages = (len(items) + page_size - 1) // page_size if items else 0

    def get_page(self, page: int) -> List[T]:
        """
        Получить элементы для указанной страницы.

        :param page: Номер страницы (начиная с 0)
        :return: Список элементов на странице
        """
        if page < 0 or (page >= self.total_pages and self.total_pages > 0):
            raise ValueError(f"Page {page} is out of range (0-{self.total_pages - 1})")

        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.items))

        return self.items[start_idx:end_idx]

    def has_prev(self, page: int) -> bool:
        """
        Проверяет, есть ли предыдущая страница.

        :param page: Текущий номер страницы
        :return: True, если есть предыдущая страница
        """
        return page > 0

    def has_next(self, page: int) -> bool:
        """
        Проверяет, есть ли следующая страница.

        :param page: Текущий номер страницы
        :return: True, если есть следующая страница
        """
        return page < self.total_pages - 1

    def get_page_info(self, page: int) -> str:
        """
        Возвращает информацию о текущей странице.

        :param page: Текущий номер страницы
        :return: Строка с информацией о странице
        """
        return f"Страница {page + 1} из {self.total_pages}" if self.total_pages > 0 else "Нет элементов"