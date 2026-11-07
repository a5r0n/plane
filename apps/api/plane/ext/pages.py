# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project pages through the v1 API (API key), reusing the web app's page view."""

import base64
import json
import os

import requests
from django.conf import settings
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.fields import ArrayField
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, UUIDField, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.api.rate_limit import ApiKeyRateThrottle
from plane.app.permissions import ROLE, ProjectPagePermission
from plane.app.serializers import PageDetailSerializer, PageSerializer
from plane.app.views.page.base import PageViewSet
from plane.bgtasks.page_transaction_task import page_transaction
from plane.bgtasks.page_version_task import track_page_version
from plane.db.models import Page, Project, ProjectMember, UserFavorite
from plane.utils.content_validator import validate_html_content
from plane.utils.exception_logger import log_exception
from plane.utils.url import normalize_url_path

LIVE_CONTENT_MEDIA_TYPE = "application/vnd.squadron.page-content+json"
LIVE_TIMEOUT_SECONDS = 10

# fields the API may set besides name and content; the rest of the SDK's fields are read-only here
WRITABLE_FIELDS = ("access", "color", "is_locked", "view_props", "logo_props", "external_id", "external_source")


class LiveUnavailable(Exception):
    pass


def write_through_live(page, description_html, name):
    """Has the live server apply new content to the page's document; returns the formats to store."""
    live_url = settings.LIVE_URL
    secret = os.environ.get("LIVE_SERVER_SECRET_KEY")
    if not live_url or not secret:
        raise LiveUnavailable("LIVE_BASE_URL or LIVE_SERVER_SECRET_KEY is not set")
    stored = bytes(page.description_binary) if page.description_binary else None
    payload = {
        "description_html": description_html,
        "name": name,
        "description_binary": base64.b64encode(stored).decode() if stored else None,
        # a page never opened in the editor has no binary yet; live builds it from these
        "stored_html": None if stored else page.description_html,
        "stored_name": None if stored else page.name,
    }
    try:
        response = requests.post(
            normalize_url_path(f"{live_url}/squadron/pages/{page.id}/content/"),
            data=json.dumps(payload),
            headers={"content-type": LIVE_CONTENT_MEDIA_TYPE, "live-server-secret-key": secret},
            timeout=LIVE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
        return {
            "description_binary": base64.b64decode(result["description_binary"]),
            "description_html": result["description_html"],
            "description_json": result["description_json"],
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise LiveUnavailable(str(e)) from e


class PageAPISerializer(PageDetailSerializer):
    description_stripped = serializers.CharField(read_only=True)
    parent_id = serializers.UUIDField(read_only=True)
    projects = serializers.SerializerMethodField()
    collection_id = serializers.SerializerMethodField()
    page_collection_id = serializers.SerializerMethodField()

    class Meta(PageDetailSerializer.Meta):
        fields = PageDetailSerializer.Meta.fields + [
            "description_stripped",
            "parent_id",
            "projects",
            "collection_id",
            "page_collection_id",
            "external_id",
            "external_source",
        ]

    def get_projects(self, obj):
        return [str(project_id) for project_id in getattr(obj, "project_ids", [])]

    # collections are a commercial feature; always null on CE
    def get_collection_id(self, obj):
        return None

    def get_page_collection_id(self, obj):
        return None


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message}, status=code)


class ProjectPageAPIEndpoint(PageViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, ProjectPagePermission]

    def get_throttles(self):
        return [ApiKeyRateThrottle()]

    def _guest_sees_own_only(self):
        slug, project_id = self.kwargs.get("slug"), self.kwargs.get("project_id")
        return (
            ProjectMember.objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                member=self.request.user,
                role=ROLE.GUEST.value,
                is_active=True,
            ).exists()
            and not Project.objects.filter(pk=project_id, guest_view_all_features=True).exists()
        )

    def _scoped(self):
        """Pages of this project the caller can see, child and archived pages included."""
        queryset = Page.objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            project_pages__project_id=self.kwargs.get("project_id"),
            project_pages__deleted_at__isnull=True,
            project_pages__project__archived_at__isnull=True,
        ).filter(Q(owned_by=self.request.user) | Q(access=Page.PUBLIC_ACCESS))
        if self._guest_sees_own_only():
            queryset = queryset.filter(owned_by=self.request.user)
        return queryset

    def get_queryset(self):
        favorites = UserFavorite.objects.filter(
            user=self.request.user,
            entity_type="page",
            entity_identifier=OuterRef("pk"),
            workspace__slug=self.kwargs.get("slug"),
        )
        empty = Value([], output_field=ArrayField(UUIDField()))
        return (
            Page.objects.filter(pk__in=self._scoped().values("pk"))
            .select_related("workspace", "owned_by")
            .annotate(is_favorite=Exists(favorites))
            .annotate(
                label_ids=Coalesce(
                    ArrayAgg(
                        "page_labels__label_id",
                        distinct=True,
                        filter=Q(page_labels__deleted_at__isnull=True, page_labels__label_id__isnull=False),
                    ),
                    empty,
                ),
                project_ids=Coalesce(
                    ArrayAgg(
                        "project_pages__project_id",
                        distinct=True,
                        filter=Q(project_pages__deleted_at__isnull=True),
                    ),
                    empty,
                ),
            )
            .order_by("-created_at", "id")
        )

    def _respond(self, page_id, code=status.HTTP_200_OK):
        return Response(PageAPISerializer(self.get_queryset().get(pk=page_id)).data, status=code)

    def list(self, request, slug, project_id):
        return self.paginate(
            request=request,
            queryset=self.get_queryset(),
            on_results=lambda pages: PageAPISerializer(pages, many=True).data,
            default_per_page=100,
            max_per_page=100,
        )

    def retrieve(self, request, slug, project_id, page_id):
        return self._respond(page_id)

    def create(self, request, slug, project_id):
        name, html = request.data.get("name"), request.data.get("description_html")
        if not isinstance(name, str) or not isinstance(html, str):
            return _error("name and description_html are required")
        is_valid, message, clean_html = validate_html_content(html)
        if not is_valid:
            return _error(message)
        clean_html = clean_html or "<p></p>"

        parent_id = request.data.get("parent_id")
        if parent_id:
            try:
                parent_exists = self._scoped().filter(pk=parent_id).exists()
            except Exception:
                parent_exists = False
            if not parent_exists:
                return _error("parent_id must be a page in this project")

        data = {key: request.data[key] for key in WRITABLE_FIELDS if key in request.data}
        serializer = PageSerializer(
            data={**data, "name": name, "parent": parent_id},
            context={
                "project_id": project_id,
                "owned_by_id": request.user.id,
                "description_json": {},
                "description_binary": None,
                "description_html": clean_html,
            },
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        page = serializer.save()
        external = {key: data[key] for key in ("external_id", "external_source") if key in data}
        if external:
            Page.objects.filter(pk=page.id).update(**external)
        page_transaction.delay(new_description_html=clean_html, old_description_html=None, page_id=str(page.id))
        return self._respond(page.id, status.HTTP_201_CREATED)

    def partial_update(self, request, slug, project_id, page_id):
        html, name = request.data.get("description_html"), request.data.get("name")
        if (html is not None and not isinstance(html, str)) or (name is not None and not isinstance(name, str)):
            return _error("name and description_html must be strings")
        if html is not None:
            is_valid, message, clean_html = validate_html_content(html)
            if not is_valid:
                return _error(message)
            html = clean_html or "<p></p>"

        with transaction.atomic():
            if not self._scoped().filter(pk=page_id).exists():
                raise Page.DoesNotExist
            page = Page.objects.select_for_update().get(pk=page_id)

            if page.archived_at:
                return _error("Page is archived")
            if page.is_locked and request.data.get("is_locked") is not False:
                return _error("Page is locked")
            changes_access = "access" in request.data and request.data["access"] != page.access
            if changes_access and page.owned_by_id != request.user.id:
                return _error("Access cannot be updated since this page is owned by someone else")

            data = {key: request.data[key] for key in WRITABLE_FIELDS if key in request.data}
            if name is not None:
                data["name"] = name
            serializer = PageSerializer(page, data=data, partial=True)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            old_html = page.description_html
            if html is not None or (name is not None and name != page.name):
                try:
                    content = write_through_live(page, html, name)
                except LiveUnavailable as e:
                    log_exception(e)
                    return _error("The live server could not apply the change", status.HTTP_502_BAD_GATEWAY)
                for key, value in content.items():
                    setattr(page, key, value)
            serializer.save()  # saves the content set above too

        if html is not None:
            track_page_version.delay(
                page_id=str(page.id),
                existing_instance=json.dumps({"description_html": old_html}),
                user_id=request.user.id,
            )
            page_transaction.delay(
                new_description_html=page.description_html, old_description_html=old_html, page_id=str(page.id)
            )
        return self._respond(page.id)

    def update(self, request, slug, project_id, page_id):
        return self.partial_update(request, slug, project_id, page_id)
