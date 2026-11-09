/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { draggable, dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { attachClosestEdge, extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge";
import { Pencil, Trash2 } from "lucide-react";
import { CustomMenu, DragHandle, DropIndicator } from "@plane/ui";
import { cn } from "@plane/utils";
import { PROPERTY_ICONS } from "../icons";
import type { TProperty } from "../types";

type TEdge = "top" | "bottom";

type Props = {
  prop: TProperty;
  onEdit: () => void;
  onDelete: () => void;
  onDrop: (sourceId: string, targetId: string, edge: TEdge) => void;
};

const ROLE_BADGE: Record<number, string | undefined> = { 20: "Admins only", 5: "Guests can set" };

function Badge({ children }: { children: string }) {
  return <span className="rounded-sm bg-layer-1 px-1.5 py-0.5 text-11 text-secondary">{children}</span>;
}

/** One definition in settings: drag handle, icon, name, key, badges and a menu. */
export function PropertyRow({ prop, onEdit, onDelete, onDrop }: Props) {
  const rowRef = useRef<HTMLDivElement | null>(null);
  const handleRef = useRef<HTMLButtonElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [edge, setEdge] = useState<TEdge | null>(null);
  const Icon = PROPERTY_ICONS[prop.type];

  useEffect(() => {
    const element = rowRef.current;
    if (!element) return;
    return combine(
      draggable({
        element,
        dragHandle: handleRef.current ?? undefined,
        getInitialData: () => ({ propertyId: prop.id }),
        onDragStart: () => setDragging(true),
        onDrop: () => setDragging(false),
      }),
      dropTargetForElements({
        element,
        canDrop: ({ source }) => typeof source.data.propertyId === "string" && source.data.propertyId !== prop.id,
        getData: ({ input, element: el }) =>
          attachClosestEdge({ propertyId: prop.id }, { input, element: el, allowedEdges: ["top", "bottom"] }),
        onDrag: ({ self }) => setEdge(extractClosestEdge(self.data) as TEdge | null),
        onDragLeave: () => setEdge(null),
        onDrop: ({ self, source }) => {
          const dropped = extractClosestEdge(self.data) as TEdge | null;
          setEdge(null);
          if (dropped) onDrop(source.data.propertyId as string, prop.id, dropped);
        },
      })
    );
  }, [prop.id, onDrop]);

  const role = ROLE_BADGE[prop.write_role];
  return (
    <div ref={rowRef}>
      <DropIndicator classNames="my-1" isVisible={edge === "top"} />
      <div
        className={cn("group flex items-center gap-2 rounded-sm px-1 py-3", { "opacity-60": dragging })}
        title={prop.description || undefined}
      >
        <DragHandle className={cn("opacity-0 group-hover:opacity-100", { "opacity-100": dragging })} ref={handleRef} />
        <Icon className="size-4 shrink-0 text-tertiary" />
        <span className="truncate text-13 text-primary">{prop.name}</span>
        <span className="font-mono text-11 text-tertiary">{prop.key}</span>
        <div className="flex items-center gap-1">
          {!prop.visible && <Badge>Hidden</Badge>}
          {role && <Badge>{role}</Badge>}
          {prop.multiple && <Badge>Multiple</Badge>}
        </div>
        <div className="ml-auto opacity-0 group-hover:opacity-100">
          <CustomMenu ellipsis useCaptureForOutsideClick ariaLabel={`${prop.name} actions`}>
            <CustomMenu.MenuItem onClick={onEdit}>
              <span className="flex items-center gap-2">
                <Pencil className="size-4" />
                Edit
              </span>
            </CustomMenu.MenuItem>
            <CustomMenu.MenuItem onClick={onDelete}>
              <span className="flex items-center gap-2 text-danger-primary">
                <Trash2 className="size-4" />
                Delete
              </span>
            </CustomMenu.MenuItem>
          </CustomMenu>
        </div>
      </div>
      <DropIndicator classNames="my-1" isVisible={edge === "bottom"} />
    </div>
  );
}
