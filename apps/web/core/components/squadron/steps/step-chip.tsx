/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TIssue } from "@plane/types";
import { cn, getFileURL } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useUser } from "@/hooks/store/user";
// local imports
import { formatWhen, isWaiting, stepTone, TONE_CLASSES } from "./helpers";
import { StepActor } from "./track/actor";
import type { TActor } from "./track/types";
import type { TStepSummary } from "./types";

type Props = { summary: TStepSummary | null | undefined; viewerId?: string; actor?: TActor; className?: string };

/** "n/m · <current step>" with its actor; amber on the viewer's turn, red when failed. */
export function StepChip({ summary, viewerId, actor, className }: Props) {
  if (!summary) return null;
  const { done, total, current } = summary;
  const tone = stepTone(current, viewerId);
  const waiting = current?.not_before && isWaiting(current) ? ` · waiting until ${formatWhen(current.not_before)}` : "";
  return (
    <div
      className={cn(
        "flex h-5 max-w-full min-w-0 items-center gap-1 rounded-sm border px-1.5 text-11",
        TONE_CLASSES[tone],
        className
      )}
      title={`${done} of ${total} steps done or skipped${current ? ` · current: ${current.title}${waiting}` : ""}`}
      data-tone={tone}
    >
      <span className="shrink-0 font-medium">
        {done}/{total}
      </span>
      {current && <span className="truncate">· {current.title}</span>}
      <StepActor actor={actor} />
    </div>
  );
}

/** The chip for a list row or board card, from the row's `step_summary`. */
export const IssueStepChip = observer(function IssueStepChip({
  issue,
  className,
}: {
  issue: TIssue;
  className?: string;
}) {
  const { getUserDetails } = useMember();
  const { data: viewer } = useUser();
  const summary = (issue as TIssue & { step_summary?: TStepSummary | null }).step_summary;
  const user = summary?.current?.actor ? getUserDetails(summary.current.actor) : undefined;
  const actor = user && {
    id: user.id,
    name: user.display_name,
    avatarUrl: getFileURL(user.avatar_url ?? ""),
    isBot: !!user.is_bot,
  };
  return <StepChip summary={summary} viewerId={viewer?.id} actor={actor} className={className} />;
});
