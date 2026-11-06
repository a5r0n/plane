# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.apps import apps
from django.urls import URLResolver

from plane import urls


@pytest.mark.unit
def test_ext_app_is_installed():
    assert apps.get_app_config("squadron_ext").name == "plane.ext"


@pytest.mark.unit
def test_ext_urls_mount_before_upstream():
    modules = [p.urlconf_module.__name__ for p in urls.urlpatterns if isinstance(p, URLResolver)]
    assert modules.index("plane.ext.urls") < modules.index("plane.app.urls")
