/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Button } from "@plane/propel/button";
import { cn } from "@plane/utils";
import { TONE_CLASSES } from "./helpers";
import type { TStep } from "./types";
import { BottomSheet } from "./track/bottom-sheet";
import { FinishForm } from "./track/finish-form";
import type { TOutcome } from "./track/types";

type Props = {
  step: TStep;
  onFinish: (status: TOutcome | "skipped", note?: string) => void;
  onRetry: () => void;
};

/** Phone widths only: the viewer's current step, pinned to the bottom of the screen. */
export function YourTurnBar({ step, onFinish, onRetry }: Props) {
  const [finishing, setFinishing] = useState<TOutcome | null>(null);
  const failed = step.status === "failed";
  return (
    <>
      <div
        className={cn(
          "fixed inset-x-0 bottom-0 z-40 flex flex-col gap-2 border-t p-3 md:hidden",
          TONE_CLASSES[failed ? "failed" : "turn"],
          "bg-surface-1"
        )}
      >
        <button
          type="button"
          className="truncate text-left text-14 font-medium text-primary"
          onClick={() => document.getElementById(`step-card-${step.id}`)?.scrollIntoView({ behavior: "smooth" })}
        >
          {failed ? "Failed" : "Your turn"}: {step.title}
        </button>
        <div className="grid grid-cols-3 gap-2">
          {failed ? (
            <Button size="xl" onClick={onRetry}>
              Retry
            </Button>
          ) : (
            <>
              <Button size="xl" onClick={() => setFinishing("done")}>
                Done
              </Button>
              <Button size="xl" variant="error-outline" onClick={() => setFinishing("failed")}>
                Failed
              </Button>
            </>
          )}
          <Button size="xl" variant="secondary" onClick={() => onFinish("skipped")}>
            Skip
          </Button>
        </div>
      </div>
      {finishing && (
        <BottomSheet title={step.title} onClose={() => setFinishing(null)}>
          <FinishForm
            outcome={finishing}
            onCancel={() => setFinishing(null)}
            onSubmit={(note) => {
              setFinishing(null);
              onFinish(finishing, note);
            }}
          />
        </BottomSheet>
      )}
    </>
  );
}
