/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Plus } from "lucide-react";
import { Button } from "@plane/propel/button";
import { Input } from "@plane/ui";
import type { TOption } from "../types";

type Props = { options: TOption[]; error?: string; onChange: (options: TOption[]) => void };

/** A choice property's options: rename, disable/enable, remove, add. New options carry no id. */
export function OptionsEditor({ options, error, onChange }: Props) {
  const patch = (index: number, change: Partial<TOption>) =>
    onChange(options.map((option, i) => (i === index ? { ...option, ...change } : option)));

  return (
    <div className="flex flex-col gap-2" data-options>
      <span className="text-13 font-medium text-secondary">Options</span>
      {options.map((option, index) => {
        const name = option.label || `option ${index + 1}`;
        return (
          // oxlint-disable-next-line no-array-index-key -- new options have no id yet
          <div key={option.id ?? `new-${index}`} className="flex items-center gap-2">
            <Input
              aria-label={`Option ${index + 1}`}
              value={option.label}
              onChange={(e) => patch(index, { label: e.target.value })}
              className="flex-1"
            />
            {option.disabled && <span className="text-11 text-tertiary">Disabled</span>}
            <Button
              variant="tertiary"
              size="sm"
              aria-label={`${option.disabled ? "Enable" : "Disable"} ${name}`}
              onClick={() => patch(index, { disabled: !option.disabled })}
            >
              {option.disabled ? "Enable" : "Disable"}
            </Button>
            <Button
              variant="tertiary"
              size="sm"
              aria-label={`Remove ${name}`}
              onClick={() => onChange(options.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </div>
        );
      })}
      <Button
        variant="tertiary"
        size="sm"
        className="self-start"
        prependIcon={<Plus />}
        onClick={() => onChange([...options, { label: "", disabled: false }])}
      >
        Add option
      </Button>
      {error && <p className="text-12 text-danger-primary">{error}</p>}
    </div>
  );
}
