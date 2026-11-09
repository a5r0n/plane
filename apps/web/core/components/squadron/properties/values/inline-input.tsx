/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { Pencil } from "lucide-react";
import { cn } from "@plane/utils";
import { formatValue } from "../helpers";
import type { TProperty, TValue } from "../types";

type Props = { prop: TProperty; value: TValue; onChange: (value: TValue) => void };

const parse = (prop: TProperty, text: string): TValue | undefined => {
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (prop.type !== "number") return trimmed;
  const number = Number(trimmed);
  return Number.isFinite(number) ? number : undefined;
};

/** Text, url and number: click to edit; Enter or blur saves, Esc cancels. */
export function InlineInput({ prop, value, onChange }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [invalid, setInvalid] = useState(false);
  const shown = formatValue(prop, value);
  const input = useRef<HTMLInputElement>(null);
  const editing = draft !== null;

  useEffect(() => {
    if (editing) input.current?.focus();
  }, [editing]);

  const open = () => {
    setDraft(value === null ? "" : String(value));
    setInvalid(false);
  };
  const close = () => {
    setDraft(null);
    setInvalid(false);
  };
  const save = () => {
    if (draft === null) return;
    const next = parse(prop, draft);
    if (next === undefined) return setInvalid(true);
    close();
    if (next !== value) onChange(next);
  };

  if (draft !== null)
    return (
      <input
        ref={input}
        aria-label={prop.name}
        aria-invalid={invalid}
        inputMode={prop.type === "number" ? "decimal" : undefined}
        className={cn(
          "h-7.5 w-full rounded-sm border border-subtle bg-transparent px-2 text-13 outline-none focus:border-accent-strong",
          { "border-danger-strong focus:border-danger-strong": invalid }
        )}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setInvalid(false);
        }}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            e.stopPropagation();
            close();
          }
        }}
      />
    );

  if (prop.type === "url" && shown)
    return (
      <div className="group flex h-7.5 w-full items-center gap-1 px-2 text-13">
        <a
          href={shown}
          target="_blank"
          rel="noopener noreferrer"
          className="truncate text-accent-primary hover:underline"
        >
          {shown}
        </a>
        <button
          type="button"
          aria-label={`Edit ${prop.name}`}
          className="hidden shrink-0 text-tertiary group-hover:block hover:text-primary"
          onClick={open}
        >
          <Pencil className="h-3 w-3" />
        </button>
      </div>
    );

  return (
    <button
      type="button"
      className={cn("h-7.5 w-full truncate rounded-sm px-2 text-left text-13 hover:bg-layer-1", {
        "text-placeholder": !shown,
      })}
      onClick={open}
    >
      {shown ?? `Add ${prop.name}`}
    </button>
  );
}
