/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Button } from "@plane/propel/button";
import { focusOnMount } from "../helpers";
import type { TOutcome } from "./types";

type Props = { outcome: TOutcome; onSubmit: (note: string) => void; onCancel: () => void };

/** Note for a finished step; Failed needs one. */
export function FinishForm({ outcome, onSubmit, onCancel }: Props) {
  const [note, setNote] = useState("");
  const failed = outcome === "failed";
  const blocked = failed && !note.trim();
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (!blocked) onSubmit(note.trim());
      }}
    >
      <textarea
        ref={focusOnMount}
        aria-label="Note"
        className="min-h-16 w-full rounded-md border border-subtle bg-layer-1 p-2 text-13 text-primary outline-none placeholder:text-placeholder"
        placeholder={failed ? "What went wrong? (required)" : "Note (optional)"}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && onCancel()}
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="lg" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant={failed ? "error-fill" : "primary"} size="lg" disabled={blocked}>
          {failed ? "Mark failed" : "Mark done"}
        </Button>
      </div>
    </form>
  );
}
