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
import { formatValue } from "./helpers";
import { useProperties } from "./use-properties";

type Props = { activityId: string; ends: "top" | "bottom" | undefined };

/** A `field: custom_fields` row in the item's history. */
export const IssuePropertyActivity = observer(function IssuePropertyActivity({ activityId, ends }: Props) {
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const properties = useProperties();
  const activity = getActivityById(activityId);
  if (!activity) return null;
  const prop = properties.definitions(activity.project)?.find((def) => def.id === activity.new_identifier);
  // datetimes come as ISO text; anything else, or an unloaded definition, shows as stored
  const show = (text?: string) =>
    prop?.type === "datetime" && text && !Number.isNaN(Date.parse(text)) ? (formatValue(prop, text) ?? text) : text;
  const { verb, name, from: rawFrom, to: rawTo } = describePropertyActivity(activity);
  const from = show(rawFrom);
  const to = show(rawTo);
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
