"""
Custom middleware for people app.
"""


class DisableCSRFForAPIMiddleware:
    """
    Disable CSRF for /api/ paths. The REST API uses JWT/Session auth.
    JWT is not vulnerable to CSRF (token in header, not cookie).
    Session auth is protected by SameSite cookies for cross-site requests.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        return self.get_response(request)
