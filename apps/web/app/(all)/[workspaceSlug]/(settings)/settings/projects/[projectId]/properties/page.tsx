/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { EUserPermissions, EUserPermissionsLevel, PROJECT_SETTINGS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Breadcrumbs } from "@plane/ui";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { PROJECT_SETTINGS_ICONS } from "@/components/settings/project/sidebar/item-icon";
import { PropertiesSettings } from "@/components/squadron/properties/settings/properties-settings";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";

function PropertiesHeader() {
  const { t } = useTranslation();
  const Icon = PROJECT_SETTINGS_ICONS.properties;
  return (
    <SettingsPageHeader
      leftItem={
        <Breadcrumbs>
          <Breadcrumbs.Item
            component={
              <BreadcrumbLink
                label={t(PROJECT_SETTINGS.properties.i18n_label)}
                icon={<Icon className="size-4 text-tertiary" />}
              />
            }
          />
        </Breadcrumbs>
      }
    />
  );
}

function PropertiesSettingsPage() {
  const { workspaceSlug, projectId } = useParams();
  const { currentProjectDetails } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const pageTitle = currentProjectDetails?.name ? `${currentProjectDetails.name} - Properties` : undefined;

  if (workspaceUserInfo && !isAdmin) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  return (
    <SettingsContentWrapper header={<PropertiesHeader />}>
      <PageHead title={pageTitle} />
      {workspaceSlug && projectId && (
        <PropertiesSettings workspaceSlug={workspaceSlug.toString()} projectId={projectId.toString()} />
      )}
    </SettingsContentWrapper>
  );
}

export default observer(PropertiesSettingsPage);
