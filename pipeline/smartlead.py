"""Talks to Smartlead. Your API key is passed in; it is never stored or printed."""

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("SMARTLEAD_BASE_URL", "https://server.smartlead.ai/api/v1")
BATCH_SIZE = 100  # leads per upload request


class SmartleadError(Exception):
    pass


def _ssl_context():
    try:
        import certifi  # present on most Macs with Python from python.org
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _call(method, path, api_key, body=None):
    url = "%s%s?%s" % (BASE_URL, path, urllib.parse.urlencode({"api_key": api_key}))
    data = json.dumps(body).encode() if body is not None else None
    last_problem = ""
    for attempt in range(4):
        request = urllib.request.Request(url, data=data, method=method,
                                         headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
                text = response.read().decode() or "{}"
                return json.loads(text)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (401, 403):
                raise SmartleadError("Smartlead rejected the API key (error %s). Check SMARTLEAD_API_KEY in your .env file." % e.code)
            if e.code == 404:
                raise SmartleadError("Smartlead could not find that campaign (error 404). Check campaign_id in settings.ini.")
            if e.code == 429 or e.code >= 500:
                last_problem = "Smartlead is busy or having trouble (error %s)" % e.code
            else:
                raise SmartleadError("Smartlead said no (error %s): %s" % (e.code, detail))
        except ssl.SSLError:
            raise SmartleadError(
                "Your Mac could not make a secure connection. Open Finder > Applications > Python 3.x "
                "and double-click 'Install Certificates.command', then try again.")
        except urllib.error.URLError as e:
            last_problem = "Could not reach Smartlead (%s). Is the internet connected?" % e.reason
        if attempt < 3:
            time.sleep(2 ** (attempt + 1))  # wait 2, 4, 8 seconds, then retry
    raise SmartleadError(last_problem + " Tried 4 times.")


def list_campaigns(api_key):
    result = _call("GET", "/campaigns", api_key)
    return result if isinstance(result, list) else result.get("data", [])


def get_campaign(api_key, campaign_id):
    return _call("GET", "/campaigns/%s" % campaign_id, api_key)


def to_smartlead(lead):
    """The shape Smartlead expects for one lead."""
    return {
        "first_name": lead["first_name"],
        "last_name": lead["last_name"],
        "email": lead["email"],
        "location": ", ".join(p for p in (lead["city"], lead["state"]) if p),
        "custom_fields": {
            "property_address": lead["property_address"],
            "city": lead["city"],
            "state": lead["state"],
            "zip": lead["zip"],
            "video_url": "",  # filled in later with the HeyGen video link
        },
    }


SAFETY_SETTINGS = {
    # False = Smartlead keeps checking these lists. Leave them all False.
    "ignore_global_block_list": False,
    "ignore_unsubscribe_list": False,
    "ignore_community_bounce_list": False,
    "ignore_duplicate_leads_in_other_campaign": False,
}


def upload_batch(api_key, campaign_id, leads):
    body = {"lead_list": [to_smartlead(l) for l in leads], "settings": SAFETY_SETTINGS}
    result = _call("POST", "/campaigns/%s/leads" % campaign_id, api_key, body)
    if isinstance(result, dict) and result.get("ok") is False:
        raise SmartleadError("Smartlead did not accept the upload: %s" % json.dumps(result)[:300])
    return result
