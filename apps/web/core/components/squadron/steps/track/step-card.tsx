/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Button } from "@plane/propel/button";
import { cn } from "@plane/utils";
import { formatWhen, isWaiting, TONE_CLASSES } from "../helpers";
import type { TStep, TStepTone } from "../types";
import { StepActor } from "./actor";
import { FinishForm } from "./finish-form";
import type { TActor, TOutcome } from "./types";

type Props = {
  step: TStep;
  actor?: TActor;
  tone: TStepTone;
  disabled?: boolean;
  menu?: React.ReactNode;
  onFinish: (status: TOutcome | "skipped", note?: string) => void;
  onRetry: () => void;
  onStartNow: () => void;
};

/** The current step, open: Finish / Failed / Skip, or Retry / Skip once failed. */
export function StepCard({ step, actor, tone, disabled, menu, onFinish, onRetry, onStartNow }: Props) {
  const [finishing, setFinishing] = useState<TOutcome | null>(null);
  const failed = step.status === "failed";
  return (
    <div id={`step-card-${step.id}`} className={cn("flex flex-col gap-2 rounded-md border p-3", TONE_CLASSES[tone])}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-13 font-medium text-primary">{step.title}</div>
          {step.detail && <div className="mt-1 text-13 whitespace-pre-wrap text-secondary">{step.detail}</div>}
        </div>
        <StepActor actor={actor} showName />
        {menu}
      </div>
      {failed && step.note && (
        <div className="rounded-sm bg-danger-subtle px-2 py-1 text-13 text-danger-primary">Failed: {step.note}</div>
      )}
      {step.not_before && isWaiting(step) && (
        <div className="flex items-center gap-2 text-12 text-tertiary">
          <span>Waiting until {formatWhen(step.not_before)}</span>
          {!disabled && (
            <Button variant="link" size="sm" onClick={onStartNow}>
              Start now
            </Button>
          )}
        </div>
      )}
      {!disabled &&
        (finishing ? (
          <FinishForm
            outcome={finishing}
            onCancel={() => setFinishing(null)}
            onSubmit={(note) => {
              setFinishing(null);
              onFinish(finishing, note);
            }}
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            {failed ? (
              <Button size="lg" onClick={onRetry}>
                Retry
              </Button>
            ) : (
              <>
                <Button size="lg" onClick={() => setFinishing("done")}>
                  Finish
                </Button>
                <Button size="lg" variant="error-outline" onClick={() => setFinishing("failed")}>
                  Failed
                </Button>
              </>
            )}
            <Button size="lg" variant="ghost" onClick={() => onFinish("skipped")}>
              Skip
            </Button>
          </div>
        ))}
    </div>
  );
}
