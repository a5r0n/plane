# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from unittest.mock import patch

import pytest

from plane.bgtasks.page_version_task import track_page_version
from plane.db.models import Page, PageVersion


def _make_page(workspace, owner):
    return Page.objects.create(
        workspace=workspace,
        owned_by=owner,
        name="Versioned page",
        description_html="<p>first</p>",
        description_json={"type": "doc", "content": [{"type": "paragraph"}]},
    )


def _track(page, old_html, user):
    with patch("plane.bgtasks.page_version_task.log_exception") as log_exception:
        track_page_version(
            page_id=str(page.id),
            existing_instance=json.dumps({"description_html": old_html}),
            user_id=str(user.id),
        )
    log_exception.assert_not_called()


@pytest.mark.unit
@pytest.mark.django_db
class TestTrackPageVersion:
    def test_first_save_creates_version(self, workspace, create_user):
        page = _make_page(workspace, create_user)

        _track(page, "<p></p>", create_user)

        version = PageVersion.objects.get(page=page)
        assert version.description_html == "<p>first</p>"
        assert version.description_json == page.description_json
        assert version.owned_by_id == create_user.id

    def test_second_save_within_window_updates_version(self, workspace, create_user):
        page = _make_page(workspace, create_user)
        _track(page, "<p></p>", create_user)

        page.description_html = "<p>second</p>"
        page.description_json = {"type": "doc", "content": [{"type": "heading"}]}
        page.save()
        _track(page, "<p>first</p>", create_user)

        version = PageVersion.objects.get(page=page)
        assert version.description_html == "<p>second</p>"
        assert version.description_json == {"type": "doc", "content": [{"type": "heading"}]}

    def test_unchanged_html_creates_no_version(self, workspace, create_user):
        page = _make_page(workspace, create_user)

        _track(page, "<p>first</p>", create_user)

        assert not PageVersion.objects.filter(page=page).exists()
