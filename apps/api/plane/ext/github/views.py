# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The GitHub App webhook endpoint: check the signature, queue the work, answer at once."""

import hashlib
import hmac
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from plane.ext.github import config
from plane.ext.github.tasks import github_delivery


def signed(secret, body, header):
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(header) and hmac.compare_digest(expected.encode(), header.encode())


@csrf_exempt
@require_POST
def webhook(request):
    secret = config.secret()
    if not secret:
        return HttpResponse(status=404)
    if not signed(secret, request.body, request.headers.get("X-Hub-Signature-256", "")):
        return JsonResponse({"error": "bad signature"}, status=401)
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return JsonResponse({"ok": True})
    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "bad payload"}, status=400)
    delivery = request.headers.get("X-GitHub-Delivery", "")[:64]
    if not delivery or not isinstance(payload, dict):
        return JsonResponse({"error": "bad payload"}, status=400)
    github_delivery.delay(delivery, event, payload)
    return JsonResponse({"queued": True}, status=202)
