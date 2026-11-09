/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import {
  Calendar,
  CalendarClock,
  Hash,
  Info,
  Link,
  ListChecks,
  Lock,
  ToggleLeft,
  Type,
  User,
  type LucideIcon,
} from "lucide-react";
import { observer } from "mobx-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { errorText, lockText, visibleSorted } from "./helpers";
import type { TProperty, TPropertyType, TValue } from "./types";
import { useProperties } from "./use-properties";
import { PropertyValueEditor } from "./values/value-editor";

export const PROPERTY_ICONS: Record<TPropertyType, LucideIcon> = {
  text: Type,
  number: Hash,
  boolean: ToggleLeft,
  date: Calendar,
  datetime: CalendarClock,
  choice: ListChecks,
  member: User,
  url: Link,
};

type Props = { workspaceSlug: string; projectId: string; issueId: string; disabled: boolean };

function RowHints({ prop, locked }: { prop: TProperty; locked: boolean }) {
  return (
    <>
      {prop.description && (
        <Tooltip tooltipContent={prop.description}>
          <span aria-label={prop.description} className="flex shrink-0">
            <Info className="size-3" />
          </span>
        </Tooltip>
      )}
      {locked && (
        <Tooltip tooltipContent={lockText(prop.write_role)}>
          <span aria-label={lockText(prop.write_role)} className="flex shrink-0">
            <Lock className="size-3" />
          </span>
        </Tooltip>
      )}
    </>
  );
}

/** The item's custom property rows, after Labels in the sidebar and in peek. */
export const ItemCustomProperties = observer(function ItemCustomProperties(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const store = useProperties();
  const ref = { slug: workspaceSlug, projectId, issueId };

  useEffect(() => {
    if (!store.definitions(projectId)) store.fetchDefinitions(ref).catch(() => undefined);
  }, [workspaceSlug, projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    store.fetchValues(ref).catch(() => undefined);
  }, [workspaceSlug, projectId, issueId]); // eslint-disable-line react-hooks/exhaustive-deps

  const defs = store.definitions(projectId);
  const fields = store.byIssue[issueId];
  if (!defs || !fields) return null;

  const save = (prop: TProperty, value: TValue) =>
    store
      .setValue(ref, prop.key, value)
      .catch((error: unknown) =>
        setToast({ type: TOAST_TYPE.ERROR, title: `Couldn't save ${prop.name}`, message: errorText(error, prop.key) })
      );

  return (
    <>
      {visibleSorted(defs).map((prop) => {
        const roleAllows = fields.can_write[prop.key] ?? false;
        return (
          <SidebarPropertyListItem
            key={prop.id}
            icon={PROPERTY_ICONS[prop.type]}
            label={prop.name}
            appendElement={<RowHints prop={prop} locked={!roleAllows} />}
          >
            <PropertyValueEditor
              prop={prop}
              value={fields.values[prop.key] ?? null}
              disabled={disabled || !roleAllows}
              projectId={projectId}
              onChange={(value) => void save(prop, value)}
            />
          </SidebarPropertyListItem>
        );
      })}
    </>
  );
});
