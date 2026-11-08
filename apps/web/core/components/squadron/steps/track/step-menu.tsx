/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { CustomMenu } from "@plane/ui";
import { BottomSheet } from "./bottom-sheet";
import { ACTION_LABELS } from "./actions";
import type { TStepAction } from "./actions";

type Props = { actions: TStepAction[]; onAction: (action: TStepAction) => void };

export function StepMenu({ actions, onAction }: Props) {
  return (
    <CustomMenu ellipsis placement="bottom-end" closeOnSelect buttonClassName="text-placeholder hover:text-secondary">
      {actions.map((action) => (
        <CustomMenu.MenuItem key={action} onClick={() => onAction(action)}>
          <span className={action === "delete" ? "text-danger-primary" : undefined}>{ACTION_LABELS[action]}</span>
        </CustomMenu.MenuItem>
      ))}
    </CustomMenu>
  );
}

type SheetProps = Props & { title: string; onClose: () => void };

/** The same actions as a bottom sheet with tap-sized rows (no drag on touch). */
export function StepSheet({ title, actions, onAction, onClose }: SheetProps) {
  return (
    <BottomSheet title={title} onClose={onClose}>
      <div className="flex flex-col">
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            className={`min-h-11 rounded-md px-2 text-left text-14 hover:bg-layer-transparent-hover ${action === "delete" ? "text-danger-primary" : "text-primary"}`}
            onClick={() => {
              onClose();
              onAction(action);
            }}
          >
            {ACTION_LABELS[action]}
          </button>
        ))}
      </div>
    </BottomSheet>
  );
}
