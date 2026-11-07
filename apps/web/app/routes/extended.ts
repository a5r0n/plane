/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

// squadron: epics. Layout chain must repeat core's file paths so mergeRoutes nests these inside them.
const P = "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]";
export const extendedRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(projects)/layout.tsx", [
        layout(`${P}/layout.tsx`, [
          layout(`${P}/epics/(list)/layout.tsx`, [
            route(":workspaceSlug/projects/:projectId/epics", `${P}/epics/(list)/page.tsx`),
          ]),
        ]),
      ]),
    ]),
  ]),
];
