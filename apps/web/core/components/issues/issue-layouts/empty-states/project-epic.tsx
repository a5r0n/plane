/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
// plane imports
import { EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { EmptyStateDetailed } from "@plane/propel/empty-state";
import { EUserProjectRoles } from "@plane/types";
// components
import { CreateEpicModal } from "@/components/squadron/epics/create-modal"; // squadron
// hooks
import { useUserPermissions } from "@/hooks/store/user";

// squadron: filled from upstream's empty stub
export const ProjectEpicsEmptyState = observer(function ProjectEpicsEmptyState() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const { allowPermissions } = useUserPermissions();
  const canCreate = allowPermissions(
    [EUserProjectRoles.ADMIN, EUserProjectRoles.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  return (
    <div className="relative h-full w-full overflow-y-auto">
      <EmptyStateDetailed
        assetKey="work-item"
        title={t("project_empty_state.epics.title")}
        description={t("project_empty_state.epics.description")}
        actions={[
          {
            label: t("project_empty_state.epics.cta_primary"),
            onClick: () => setIsOpen(true),
            disabled: !canCreate,
            variant: "primary",
          },
        ]}
      />
      <CreateEpicModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </div>
  );
});
