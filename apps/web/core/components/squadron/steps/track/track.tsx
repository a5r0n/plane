/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Sortable } from "@plane/ui";
import { currentStep, moveStep, stepTone } from "../helpers";
import type { TStep } from "../types";
import { stepActions } from "./actions";
import type { TStepAction } from "./actions";
import { FinishForm } from "./finish-form";
import { StepCard } from "./step-card";
import { StepEditor } from "./step-editor";
import { StepMenu, StepSheet } from "./step-menu";
import { StepRow } from "./step-row";
import type { TActor, TActorPicker, TOutcome, TStepHandlers } from "./types";

export type TTrackProps = {
  steps: TStep[];
  viewerId?: string;
  actorOf: (id: string | null) => TActor | undefined;
  disabled?: boolean;
  /** Phone widths: row menus open a bottom sheet and drag is off. */
  narrow?: boolean;
  /** Open an editor for a new step at the end (the "Add steps" button). */
  adding?: boolean;
  onAddingDone?: () => void;
  renderActorPicker?: TActorPicker;
  handlers: TStepHandlers;
};

const STATUS: Record<TOutcome | "skipped", TStep["status"]> = { done: "done", failed: "failed", skipped: "skipped" };

/** The path: done steps fold to one line, the current step opens as a card, later steps one line each. */
export function Track(props: TTrackProps) {
  const { steps, viewerId, actorOf, disabled, narrow, adding, onAddingDone, renderActorPicker, handlers } = props;
  const [showDone, setShowDone] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [inserting, setInserting] = useState<number | null>(null);
  const [failing, setFailing] = useState<string | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);

  const current = currentStep(steps);
  const currentIndex = current ? steps.indexOf(current) : steps.length;
  const folded = steps.slice(0, currentIndex);
  const open = steps.slice(currentIndex);
  const insertAt = adding && inserting === null ? steps.length : inserting;

  const finish = (step: TStep, outcome: TOutcome | "skipped", note?: string) =>
    handlers.update(step.id, note ? { status: STATUS[outcome], note } : { status: STATUS[outcome] });

  const run = (step: TStep, action: TStepAction) => {
    const index = steps.indexOf(step);
    if (action === "done" || action === "skip") return finish(step, action === "done" ? "done" : "skipped");
    if (action === "failed") return setFailing(step.id);
    if (action === "pending") return handlers.update(step.id, { status: "pending", note: "" });
    if (action === "edit") return setEditing(step.id);
    if (action === "insert-above") return setInserting(index);
    if (action === "insert-below") return setInserting(index + 1);
    if (action === "move-up" || action === "move-down")
      return handlers.reorder(moveStep(steps, step.id, action === "move-up" ? -1 : 1));
    if (action === "delete") return handlers.remove(step.id);
  };

  const menuFor = (step: TStep) => {
    if (disabled) return null;
    const actions = stepActions(step, steps.indexOf(step), steps.length);
    if (!narrow) return <StepMenu actions={actions} onAction={(action) => void run(step, action)} />;
    return (
      <button
        type="button"
        aria-label="Step actions"
        className="px-2 text-placeholder"
        onClick={() => setSheet(step.id)}
      >
        ⋯
      </button>
    );
  };

  const editor = (position: number) => (
    <StepEditor
      key={`new-${position}`}
      renderActorPicker={renderActorPicker}
      onCancel={() => {
        setInserting(null);
        onAddingDone?.();
      }}
      onSave={(data, another) => {
        void handlers.add(data, position);
        setInserting(another ? position + 1 : null);
        if (!another) onAddingDone?.();
      }}
    />
  );

  const renderStep = (step: TStep) => {
    if (editing === step.id)
      return (
        <StepEditor
          step={step}
          renderActorPicker={renderActorPicker}
          onCancel={() => setEditing(null)}
          onSave={(data) => {
            setEditing(null);
            void handlers.update(step.id, data);
          }}
        />
      );
    const failingForm = failing === step.id && (
      <div className="px-2 pb-2">
        <FinishForm
          outcome="failed"
          onCancel={() => setFailing(null)}
          onSubmit={(note) => {
            setFailing(null);
            void finish(step, "failed", note);
          }}
        />
      </div>
    );
    if (step === current)
      return (
        <>
          <StepCard
            step={step}
            actor={actorOf(step.actor)}
            tone={stepTone(step, viewerId)}
            disabled={disabled}
            menu={menuFor(step)}
            onFinish={(outcome, note) => void finish(step, outcome, note)}
            onRetry={() => void handlers.update(step.id, { status: "pending", note: "" })}
            onStartNow={() => void handlers.update(step.id, { not_before: null })}
          />
          {failingForm}
        </>
      );
    const held = current?.status === "failed" && steps.indexOf(step) > currentIndex && step.status === "pending";
    return (
      <>
        <StepRow step={step} actor={actorOf(step.actor)} held={held} menu={menuFor(step)} />
        {failingForm}
      </>
    );
  };

  const withInserts = (list: TStep[], offset: number) =>
    list.map((step, i) => (
      <div key={step.id}>
        {insertAt === offset + i && editor(offset + i)}
        {renderStep(step)}
      </div>
    ));

  const sheetStep = steps.find((step) => step.id === sheet);
  const draggable = !disabled && !narrow && editing === null && insertAt === null && open.length > 1;

  return (
    <div className="flex flex-col gap-1">
      {folded.length > 0 &&
        (showDone ? (
          withInserts(folded, 0)
        ) : (
          <button
            type="button"
            className="min-h-9 rounded-md px-2 text-left text-13 text-tertiary hover:bg-layer-transparent-hover"
            onClick={() => setShowDone(true)}
          >
            ✓ {folded.length} done
          </button>
        ))}
      {draggable ? (
        <Sortable
          data={open}
          keyExtractor={(step) => step.id}
          render={(step) => renderStep(step)}
          onChange={(next) => {
            // Sortable's monitor fires on every drop on the page; act only on a real move.
            if (next.length !== open.length || next.every((step, i) => step.id === open[i].id)) return;
            void handlers.reorder([...folded, ...next]);
          }}
        />
      ) : (
        withInserts(open, currentIndex)
      )}
      {insertAt === steps.length && editor(steps.length)}
      {sheetStep && (
        <StepSheet
          title={sheetStep.title}
          actions={stepActions(sheetStep, steps.indexOf(sheetStep), steps.length)}
          onClose={() => setSheet(null)}
          onAction={(action) => void run(sheetStep, action)}
        />
      )}
    </div>
  );
}
