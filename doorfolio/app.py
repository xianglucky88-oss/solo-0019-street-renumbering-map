from .http_service import application_for, serve
from .lookup import forward
from .lookup import reverse
from .lookup import inspect
from .registry import open_booklet, deliver, status
from .folio_lookup import booklet_forward, booklet_reverse

PREFIX = 'doorfolio'
ROUTES = {
    'forward': forward,
    'reverse': reverse,
    'inspect': inspect,
    'booklet_open': open_booklet,
    'booklet_deliver': deliver,
    'booklet_status': status,
    'booklet_forward': booklet_forward,
    'booklet_reverse': booklet_reverse,
}
application = application_for(PREFIX, ROUTES)

if __name__ == "__main__":
    serve(application, 8821)
