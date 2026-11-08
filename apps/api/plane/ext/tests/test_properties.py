# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, transaction

from plane.db.models import ProjectMember, User, WorkspaceMember
from plane.ext.models import CustomProperty, CustomValue
from plane.ext.properties import coerce, present
from plane.ext.tests.conftest import make_issue, make_project

T = CustomProperty.Type


@pytest.fixture
def project(db, workspace, create_user):
    return make_project(workspace, create_user, "Props", "PR")


@pytest.fixture
def define(project, create_user):
    def define(key, type, **fields):
        fields.setdefault("name", key.title())
        return CustomProperty.objects.create(
            project=project, workspace=project.workspace, key=key, type=type, created_by=create_user, **fields
        )

    return define


def held(prop, **column):
    return CustomValue(property=prop, **column)


@pytest.mark.unit
@pytest.mark.django_db
class TestCoerce:
    def test_text(self, define):
        prop = define("note", T.TEXT)
        assert coerce(prop, "ok") == ["ok"]
        for bad in ("a\nb", "x" * 256, 5, ["ok"]):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_number(self, define):
        prop = define("count", T.NUMBER)
        assert coerce(prop, "1.5") == [Decimal("1.5")]
        assert coerce(prop, 3) == [Decimal(3)]
        for bad in (True, "abc", float("nan")):
            with pytest.raises(ValueError):
                coerce(prop, bad)
        assert present(prop, [held(prop, value_number=Decimal("2"))]) == 2
        assert isinstance(present(prop, [held(prop, value_number=Decimal("2"))]), int)
        assert present(prop, [held(prop, value_number=Decimal("2.5"))]) == 2.5

    def test_boolean(self, define):
        prop = define("done", T.BOOLEAN)
        assert coerce(prop, False) == [False]
        with pytest.raises(ValueError):
            coerce(prop, "true")

    def test_date(self, define):
        prop = define("when", T.DATE)
        assert coerce(prop, "2026-01-02") == [date(2026, 1, 2)]
        with pytest.raises(ValueError):
            coerce(prop, "02/01/2026")
        assert present(prop, [held(prop, value_date=date(2026, 1, 2))]) == "2026-01-02"

    def test_datetime_is_stored_utc(self, define):
        prop = define("at", T.DATETIME)
        assert coerce(prop, "2026-01-01T10:00:00+02:00") == [datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)]
        assert coerce(prop, "2026-01-01T10:00:00Z") == [datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)]
        with pytest.raises(ValueError):
            coerce(prop, "2026-01-01T10:00:00")
        value = held(prop, value_datetime=datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc))
        assert present(prop, [value]) == "2026-01-01T08:00:00Z"

    def test_url(self, define):
        prop = define("pr", T.URL)
        assert coerce(prop, "https://github.com/x/y/pull/1") == ["https://github.com/x/y/pull/1"]
        for bad in ("ftp://x", "github.com/x", "https://"):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_choice(self, define):
        prop = define("repo", T.CHOICE, options=[{"id": "plane", "label": "Plane", "disabled": False}])
        assert coerce(prop, "plane") == ["plane"]
        with pytest.raises(ValueError):
            coerce(prop, "nope")

    def test_member(self, define, project, create_user, workspace):
        prop = define("owner", T.MEMBER)
        assert coerce(prop, str(create_user.id)) == [create_user.id]
        outsider = User.objects.create(email="out@plane.so", username="out")
        WorkspaceMember.objects.create(workspace=workspace, member=outsider, role=15)
        for bad in (str(outsider.id), "not-a-uuid"):
            with pytest.raises(ValueError):
                coerce(prop, bad)

    def test_multiple_takes_a_list(self, define):
        options = [{"id": i, "label": i.upper(), "disabled": False} for i in ("a", "b")]
        prop = define("tags", T.CHOICE, options=options, multiple=True)
        assert coerce(prop, ["a", "a", "b"]) == ["a", "b"]
        assert coerce(prop, None) == []
        assert coerce(prop, []) == []
        with pytest.raises(ValueError):
            coerce(prop, "a")
        assert present(prop, []) == []
        assert present(define("one", T.TEXT), []) is None

    def test_key_stays_reserved_after_delete(self, define):
        define("repo", T.TEXT).delete()
        with pytest.raises(IntegrityError), transaction.atomic():
            define("repo", T.TEXT)
