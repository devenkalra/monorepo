from dj_rest_auth.views import LogoutView as RestAuthLogoutView


class LogoutView(RestAuthLogoutView):
    """dj-rest-auth logout that never authenticates the request.

    An expired Bearer token would otherwise fail authentication with a 401
    before the session and JWT cookies are cleared, leaving /login/ to send
    the browser straight back into the app.
    """

    authentication_classes = ()
