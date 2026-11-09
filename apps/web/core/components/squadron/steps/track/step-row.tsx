/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Check, Circle, Clock, SkipForward, X } from "lucide-react";
import { cn } from "@plane/utils";
import { formatWhen } from "../helpers";
import type { TStep, TStepStatus } from "../types";
import { StepActor } from "./actor";
import type { TActor } from "./types";

const ICONS: Record<TStepStatus, React.ReactNode> = {
  pending: <Circle className="size-3.5 text-placeholder" />,
  done: <Check className="size-3.5 text-success-primary" />,
  failed: <X className="size-3.5 text-danger-primary" />,
  skipped: <SkipForward className="size-3.5 text-placeholder" />,
};

type Props = { step: TStep; actor?: TActor; held?: boolean; menu?: React.ReactNode };

/** One line per step; tap the title for its detail and note. */
export function StepRow({ step, actor, held, menu }: Props) {
  const [open, setOpen] = useState(false);
  const closed = step.status === "done" || step.status === "skipped";
  return (
    <div className="flex flex-col rounded-md px-2 hover:bg-layer-transparent-hover">
      <div className="flex min-h-9 items-center gap-2">
        {ICONS[step.status]}
        <button
          type="button"
          className={cn("min-w-0 flex-1 truncate text-left text-13", closed ? "text-tertiary" : "text-primary")}
          onClick={() => setOpen(!open)}
        >
          {step.title}
        </button>
        {held && <span className="shrink-0 text-12 text-tertiary">held by failed step</span>}
        {step.not_before && (
          <span className="flex shrink-0 items-center gap-1 text-12 text-tertiary">
            <Clock className="size-3" />
            {formatWhen(step.not_before)}
          </span>
        )}
        <StepActor actor={actor} />
        {menu}
      </div>
      {open && (step.detail || step.note) && (
        <div className="pb-2 pl-6 text-13 whitespace-pre-wrap text-secondary">
          {step.detail}
          {step.note && <div className="mt-1 text-tertiary">Note: {step.note}</div>}
        </div>
      )}
    </div>
  );
}
