from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """`?page=&page_size=` (default 20) → {count, next, previous, results} (specs/01 §6)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200
