/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { SettingsHeading } from "@/components/settings/heading";
import { dropOrder, errorText } from "../helpers";
import type { TProperty } from "../types";
import { useProperties } from "../use-properties";
import { PropertyRow } from "./property-row";

type Props = { workspaceSlug: string; projectId: string };

// "new" opens the create modal; a property opens edit or delete.
export type TModal = { kind: "edit"; prop: TProperty | null } | { kind: "delete"; prop: TProperty } | null;

/** Project settings → Properties: the project's definitions, in order. */
export const PropertiesSettings = observer(function PropertiesSettings({ workspaceSlug, projectId }: Props) {
  const store = useProperties();
  const [, setModal] = useState<TModal>(null);
  const defs = store.definitions(projectId);

  useEffect(() => {
    store
      .fetchDefinitions({ slug: workspaceSlug, projectId })
      .catch((error: unknown) =>
        setToast({ type: TOAST_TYPE.ERROR, title: "Couldn't load properties", message: errorText(error) })
      );
  }, [store, workspaceSlug, projectId]);

  const onDrop = useCallback(
    (sourceId: string, targetId: string, edge: "top" | "bottom") => {
      const order = dropOrder(store.definitions(projectId) ?? [], sourceId, targetId, edge);
      if (order === null) return;
      store
        .reorder({ slug: workspaceSlug, projectId }, sourceId, order)
        .catch((error: unknown) =>
          setToast({ type: TOAST_TYPE.ERROR, title: "Couldn't move the property", message: errorText(error) })
        );
    },
    [store, workspaceSlug, projectId]
  );

  const add = () => setModal({ kind: "edit", prop: null });

  return (
    <>
      <SettingsHeading
        title="Properties"
        description="Your own fields on this project's work items."
        control={
          <Button variant="primary" size="lg" onClick={add}>
            Add property
          </Button>
        }
      />
      <div className="mt-6 w-full">
        {defs?.length === 0 && (
          <div className="flex flex-col items-start gap-3 py-12">
            <p className="text-13 text-tertiary">No properties yet. Add one to track your own fields on work items.</p>
            <Button variant="secondary" size="sm" onClick={add}>
              Add property
            </Button>
          </div>
        )}
        {defs?.map((prop) => (
          <PropertyRow
            key={prop.id}
            prop={prop}
            onEdit={() => setModal({ kind: "edit", prop })}
            onDelete={() => setModal({ kind: "delete", prop })}
            onDrop={onDrop}
          />
        ))}
      </div>
    </>
  );
});
