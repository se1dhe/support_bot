from typing import List, TypeVar, Generic, Any, Dict

T = TypeVar('T')


class Paginator(Generic[T]):
    """
    Класс для пагинации списков элементов.
    """

    def __init__(self, items: List[T], page_size: int = 5):
        """
        Инициализирует пагинатор с указанным списком элементов.

        Args:
            items: Список элементов для пагинации
            page_size: Количество элементов на странице
        """
        self.items = items
        self.page_size = page_size
        self.total_pages = (len(items) + page_size - 1) // page_size if items else 0

    def get_page(self, page: int) -> List[T]:
        """
        Получить элементы для указанной страницы.

        Args:
            page: Номер страницы (начиная с 0)

        Returns:
            List[T]: Список элементов на странице
        """
        if page < 0 or (page >= self.total_pages and self.total_pages > 0):
            raise ValueError(f"Page {page} is out of range (0-{self.total_pages - 1})")

        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.items))

        return self.items[start_idx:end_idx]

    def has_prev(self, page: int) -> bool:
        """
        Проверяет, есть ли предыдущая страница.

        Args:
            page: Текущий номер страницы

        Returns:
            bool: True, если есть предыдущая страница
        """
        return page > 0

    def has_next(self, page: int) -> bool:
        """
        Проверяет, есть ли следующая страница.

        Args:
            page: Текущий номер страницы

        Returns:
            bool: True, если есть следующая страница
        """
        return page < self.total_pages - 1

    def get_page_info(self, page: int) -> Dict[str, Any]:
        """
        Возвращает информацию о текущей странице.

        Args:
            page: Текущий номер страницы

        Returns:
            Dict[str, Any]: Информация о странице (номер, общее количество и т.д.)
        """
        return {
            "current_page": page + 1,
            "total_pages": self.total_pages,
            "has_prev": self.has_prev(page),
            "has_next": self.has_next(page),
            "page_size": self.page_size,
            "total_items": len(self.items)
        }