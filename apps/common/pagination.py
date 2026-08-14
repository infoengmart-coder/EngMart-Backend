from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Page-number pagination that respects ``?page_size=``.

    The default DRF class ignores the query parameter, so the storefront's
    request for a larger page silently returned 24 rows — a category with 171
    products appeared to have 24. The cap keeps a single request from pulling
    the entire catalog out of a remote database.
    """
    page_size_query_param = 'page_size'
    max_page_size = 100
