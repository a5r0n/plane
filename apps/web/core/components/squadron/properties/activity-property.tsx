/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { SlidersHorizontal } from "lucide-react";
// components
import { IssueActivityBlockComponent } from "@/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { describePropertyActivity } from "./activity";

type Props = { activityId: string; ends: "top" | "bottom" | undefined };

/** A `field: custom_fields` row in the item's history. */
export const IssuePropertyActivity = observer(function IssuePropertyActivity({ activityId, ends }: Props) {
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const activity = getActivityById(activityId);
  if (!activity) return null;
  const { verb, name, from, to } = describePropertyActivity(activity);
  const bold = <span className="font-medium text-primary">{name}</span>;
  return (
    <IssueActivityBlockComponent
      icon={<SlidersHorizontal size={14} className="text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {verb} {bold}
        {verb === "set" && ` to ${to}`}
        {verb === "changed" && ` from ${from} to ${to}`}
      </>
    </IssueActivityBlockComponent>
  );
});
