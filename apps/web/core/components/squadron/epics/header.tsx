/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { WorkItemsIcon } from "@plane/propel/icons";
import { EIssuesStoreType } from "@plane/types";
import { Breadcrumbs, Header } from "@plane/ui";
import { CommonProjectBreadcrumbs } from "@/components/breadcrumbs/common";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { HeaderFilters } from "@/components/issues/filters";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { CreateEpicModal } from "./create-modal";

export const EpicsHeader = observer(function EpicsHeader() {
  const { t } = useTranslation();
  const { workspaceSlug, projectId } = useParams();
  const [isOpen, setIsOpen] = useState(false);
  const { currentProjectDetails } = useProject();
  const { allowPermissions } = useUserPermissions();
  const canCreate = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.PROJECT);

  return (
    <Header>
      <Header.LeftItem>
        <Breadcrumbs className="flex-grow-0">
          <CommonProjectBreadcrumbs workspaceSlug={workspaceSlug?.toString()} projectId={projectId?.toString()} />
          <Breadcrumbs.Item
            component={
              <BreadcrumbLink
                label={t("sidebar.epics")}
                href={`/${workspaceSlug}/projects/${projectId}/epics/`}
                icon={<WorkItemsIcon className="h-4 w-4 text-tertiary" />}
                isLast
              />
            }
            isLast
          />
        </Breadcrumbs>
      </Header.LeftItem>
      <Header.RightItem>
        <div className="hidden gap-2 md:flex">
          <HeaderFilters
            projectId={projectId}
            currentProjectDetails={currentProjectDetails}
            workspaceSlug={workspaceSlug}
            canUserCreateIssue={canCreate}
            storeType={EIssuesStoreType.EPIC}
          />
        </div>
        {canCreate && (
          <Button variant="primary" size="lg" onClick={() => setIsOpen(true)}>
            {t("project_empty_state.epics.cta_primary")}
          </Button>
        )}
      </Header.RightItem>
      <CreateEpicModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </Header>
  );
});
