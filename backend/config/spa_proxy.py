import mimetypes
import urllib.error
import urllib.request
from django.http import Http404, HttpResponse

FRONTEND_ORIGIN = "https://myfiltech.onrender.com"


def spa_proxy_view(request, path=""):
    clean_path = path.lstrip("/")

    # Static asset requests (/assets/...)
    if clean_path.startswith("assets/"):
        target_url = f"{FRONTEND_ORIGIN}/{clean_path}"
        try:
            req = urllib.request.Request(
                target_url, headers={"User-Agent": "Django-SPA-Proxy"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type")
                if not content_type:
                    content_type, _ = mimetypes.guess_type(clean_path)
                return HttpResponse(
                    resp.read(), content_type=content_type or "application/octet-stream"
                )
        except Exception:
            raise Http404()

    # All other routes (/, /login, /dashboard, etc.) return index.html for Vue Router
    try:
        req = urllib.request.Request(
            FRONTEND_ORIGIN, headers={"User-Agent": "Django-SPA-Proxy"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return HttpResponse(resp.read(), content_type="text/html; charset=utf-8")
    except Exception as e:
        return HttpResponse(
            f"Frontend loading error: {e}", status=502, content_type="text/plain"
        )
