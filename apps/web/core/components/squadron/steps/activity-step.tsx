/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { ListChecks } from "lucide-react";
// components
import { IssueActivityBlockComponent } from "@/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local imports
import { describeStepActivity } from "./activity";

type Props = { activityId: string; ends: "top" | "bottom" | undefined };

/** A `field: step` row in the item's history. */
export const IssueStepActivity = observer(function IssueStepActivity({ activityId, ends }: Props) {
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const activity = getActivityById(activityId);
  if (!activity) return null;
  const { text, title, note } = describeStepActivity(activity);
  return (
    <IssueActivityBlockComponent
      icon={<ListChecks size={14} className="text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        <span>{text} </span>
        {title && <span className="font-medium text-primary">{title}</span>}
        {note && <span> · {note}</span>}
      </>
    </IssueActivityBlockComponent>
  );
});
