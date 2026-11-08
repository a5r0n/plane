/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Button } from "@plane/propel/button";
import { focusOnMount, fromLocalInput, toLocalInput } from "../helpers";
import type { TStep, TStepInput } from "../types";
import type { TActorPicker } from "./types";

type Props = {
  step?: TStep;
  renderActorPicker?: TActorPicker;
  onSave: (data: TStepInput, another: boolean) => void;
  onCancel: () => void;
};

/** Title, detail, actor and not before; Enter in the title saves (and opens another when adding). */
export function StepEditor({ step, renderActorPicker, onSave, onCancel }: Props) {
  const [title, setTitle] = useState(step?.title ?? "");
  const [detail, setDetail] = useState(step?.detail ?? "");
  const [actor, setActor] = useState<string | null>(step?.actor ?? null);
  const [notBefore, setNotBefore] = useState(toLocalInput(step?.not_before ?? null));
  const save = (another: boolean) => {
    if (!title.trim()) return;
    onSave({ title: title.trim(), detail, actor, not_before: fromLocalInput(notBefore) }, another && !step);
  };
  return (
    <div
      role="group"
      aria-label={step ? "Edit step" : "New step"}
      className="flex flex-col gap-2 rounded-md border border-subtle bg-layer-1 p-2"
      onKeyDown={(event) => event.key === "Escape" && onCancel()}
    >
      <input
        ref={focusOnMount}
        aria-label="Step title"
        className="w-full bg-transparent text-13 font-medium text-primary outline-none placeholder:text-placeholder"
        placeholder="Step title"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            save(true);
          }
        }}
      />
      <textarea
        aria-label="Step detail"
        className="min-h-12 w-full bg-transparent text-13 text-secondary outline-none placeholder:text-placeholder"
        placeholder="Detail (optional)"
        value={detail}
        onChange={(event) => setDetail(event.target.value)}
      />
      <div className="flex flex-wrap items-center gap-2">
        {renderActorPicker?.(actor, setActor)}
        <label className="flex items-center gap-1 text-12 text-tertiary">
          Not before
          <input
            type="datetime-local"
            aria-label="Not before"
            className="rounded-sm border border-subtle bg-transparent px-1 text-12 text-secondary"
            value={notBefore}
            onChange={(event) => setNotBefore(event.target.value)}
          />
        </label>
        <div className="ml-auto flex gap-2">
          <Button type="button" variant="ghost" size="lg" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" size="lg" disabled={!title.trim()} onClick={() => save(false)}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}
