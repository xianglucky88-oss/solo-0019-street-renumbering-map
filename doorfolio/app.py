from .http_service import application_for, serve
from .lookup import forward
from .lookup import reverse
from .lookup import inspect

PREFIX = 'doorfolio'
ROUTES = {'forward': forward, 'reverse': reverse, 'inspect': inspect}
application = application_for(PREFIX, ROUTES)

if __name__ == "__main__":
    serve(application, 8821)
