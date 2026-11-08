/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Avatar } from "@plane/ui";
import type { TActor } from "./types";

type Props = { actor?: TActor; showName?: boolean };

/** Square avatar for bots, round for people. */
export function StepActor({ actor, showName = false }: Props) {
  if (!actor) return null;
  return (
    <span className="flex shrink-0 items-center gap-1 text-12 text-secondary" title={actor.name}>
      <Avatar name={actor.name} src={actor.avatarUrl} size="sm" shape={actor.isBot ? "square" : "circle"} />
      {showName && <span className="truncate">{actor.name}</span>}
    </span>
  );
}
