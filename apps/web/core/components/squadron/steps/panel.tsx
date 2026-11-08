/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ListChecks } from "lucide-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { CircularProgressIndicator, Collapsible, CollapsibleButton } from "@plane/ui";
import { getFileURL } from "@plane/utils";
// components
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { IssueDetailWidgetButton } from "@/components/issues/issue-detail-widgets/widget-button";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useUser } from "@/hooks/store/user";
// local imports
import { summarize } from "./helpers";
import { Track } from "./track/track";
import type { TActor, TStepHandlers } from "./track/types";
import type { TStepInput } from "./types";
import { useSteps } from "./use-steps";
import { YourTurnBar } from "./your-turn-bar";

type Props = { workspaceSlug: string; projectId: string; issueId: string; disabled: boolean };

const useNarrow = () => {
  const query = "(max-width: 767px)"; // below Tailwind's md
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setNarrow(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return narrow;
};

/** The item's path under the description; an item with no steps shows nothing. */
export const StepsPanel = observer(function StepsPanel({ workspaceSlug, projectId, issueId, disabled }: Props) {
  const store = useSteps();
  const { getUserDetails } = useMember();
  const { data: viewer } = useUser();
  const narrow = useNarrow();
  const [isOpen, setOpen] = useState(true);
  const ref = { slug: workspaceSlug, projectId, issueId };

  useEffect(() => {
    store.fetch({ slug: workspaceSlug, projectId, issueId }).catch(() => undefined);
  }, [store, workspaceSlug, projectId, issueId]);

  const steps = store.steps(issueId);
  const adding = !!store.adding[issueId];
  if (!steps || (steps.length === 0 && !adding)) return null;

  const report = (promise: Promise<unknown>) =>
    promise.catch((error: { error?: string; detail?: string } | undefined) =>
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Step not saved",
        message: error?.error ?? error?.detail ?? "Something went wrong. Please try again.",
      })
    );
  const handlers: TStepHandlers = {
    add: (data: TStepInput, position: number) => report(store.add(ref, data, position)),
    update: (stepId, data) => report(store.update(ref, stepId, data)),
    remove: (stepId) => report(store.remove(ref, stepId)),
    reorder: (next) => report(store.reorder(ref, next)),
  };
  const actorOf = (id: string | null): TActor | undefined => {
    const user = id ? getUserDetails(id) : undefined;
    if (!user) return undefined;
    return { id: user.id, name: user.display_name, avatarUrl: getFileURL(user.avatar_url ?? ""), isBot: !!user.is_bot };
  };

  const summary = summarize(steps);
  const current = steps.find((step) => step.id === summary?.current?.id);
  const percentage = summary ? (summary.done / summary.total) * 100 : 0;

  return (
    <>
      <Collapsible
        isOpen={isOpen}
        onToggle={() => setOpen(!isOpen)}
        buttonClassName="w-full"
        title={
          <CollapsibleButton
            isOpen={isOpen}
            title="Steps"
            indicatorElement={
              summary && (
                <div
                  className="flex max-w-[55vw] min-w-0 items-center gap-1.5 text-13 text-tertiary"
                  title="Done and skipped steps count as done"
                >
                  <CircularProgressIndicator size={18} percentage={percentage} strokeWidth={3} />
                  <span className="truncate">
                    {summary.done}/{summary.total} done{current ? ` · next: ${current.title}` : ""}
                  </span>
                </div>
              )
            }
          />
        }
      >
        <div className="py-2">
          <Track
            steps={steps}
            viewerId={viewer?.id}
            actorOf={actorOf}
            disabled={disabled}
            narrow={narrow}
            adding={adding}
            onAddingDone={() => store.setAdding(issueId, false)}
            handlers={handlers}
            renderActorPicker={(value, onChange) => (
              <MemberDropdown
                value={value}
                onChange={(actor: string | null) => onChange(actor)}
                multiple={false}
                projectId={projectId}
                buttonVariant="border-with-text"
                placeholder="Actor"
              />
            )}
          />
        </div>
      </Collapsible>
      {!disabled && current && current.actor === viewer?.id && (
        <YourTurnBar
          step={current}
          onFinish={(status, note) => void handlers.update(current.id, note ? { status, note } : { status })}
          onRetry={() => void handlers.update(current.id, { status: "pending", note: "" })}
        />
      )}
    </>
  );
});

/** "Add steps" in the widget buttons row: opens the panel with an editor. */
export const AddStepsButton = observer(function AddStepsButton({
  issueId,
  disabled,
}: {
  issueId: string;
  disabled: boolean;
}) {
  const store = useSteps();
  return (
    <button type="button" disabled={disabled} onClick={() => store.setAdding(issueId, true)}>
      <IssueDetailWidgetButton
        title="Add steps"
        icon={<ListChecks className="h-3.5 w-3.5 flex-shrink-0" strokeWidth={2} />}
        disabled={disabled}
      />
    </button>
  );
});
