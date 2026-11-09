/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Button } from "@plane/propel/button";
import { CloseIcon } from "@plane/propel/icons";
import { CustomSearchSelect } from "@plane/ui";
import type { TOption, TProperty, TValue } from "../types";

type Props = { prop: TProperty; value: TValue; onChange: (value: TValue) => void };

const labelOf = (prop: TProperty, id: string): TOption =>
  prop.options.find((option) => option.id === id) ?? { id, label: id, disabled: true };

function Chip({ option, onRemove, removeLabel }: { option: TOption; onRemove: () => void; removeLabel: string }) {
  return (
    <Button variant="tertiary" size="sm" className="group max-w-full" aria-label={removeLabel} onClick={onRemove}>
      <span className="truncate">{option.label}</span>
      {option.disabled && <span className="text-11 text-tertiary">disabled</span>}
      <CloseIcon className="h-2.5 w-2.5 shrink-0 transition-all group-hover:text-danger-primary" />
    </Button>
  );
}

/** Enabled options can be picked; a held disabled one stays (tagged) until removed. */
export function ChoiceEditor({ prop, value, onChange }: Props) {
  const held = Array.isArray(value) ? value : typeof value === "string" ? [value] : [];
  const options = prop.options
    .filter((option) => !option.disabled && option.id)
    .map((option) => ({ value: option.id as string, query: option.label, content: option.label }));

  if (prop.multiple) {
    const rest = (id: string) => held.filter((other) => other !== id);
    return (
      <div className="flex w-full flex-wrap items-center gap-1 px-1 py-0.5">
        {held.map((id) => {
          const option = labelOf(prop, id);
          return (
            <Chip
              key={id}
              option={option}
              removeLabel={`Remove ${option.label}`}
              onRemove={() => onChange(rest(id).length ? rest(id) : null)}
            />
          );
        })}
        <CustomSearchSelect
          multiple
          value={held}
          options={options}
          onChange={(ids: string[]) => onChange(ids.length ? ids : null)}
          customButton={<span className="px-1 text-13 text-placeholder">{held.length ? "+" : `Add ${prop.name}`}</span>}
          noChevron
        />
      </div>
    );
  }

  const current = held[0] ? labelOf(prop, held[0]) : null;
  return (
    <div className="group flex h-7.5 w-full items-center gap-1 px-2 text-13">
      <CustomSearchSelect
        value={held[0] ?? null}
        options={options}
        onChange={(id: string) => onChange(id)}
        className="min-w-0 grow"
        customButton={
          <span className={current ? "truncate" : "text-placeholder"}>
            {current?.label ?? `Add ${prop.name}`}
            {current?.disabled && <span className="ml-1 text-11 text-tertiary">disabled</span>}
          </span>
        }
        noChevron
      />
      {current && (
        <button
          type="button"
          aria-label={`Clear ${prop.name}`}
          className="hidden shrink-0 text-tertiary group-hover:block hover:text-danger-primary"
          onClick={() => onChange(null)}
        >
          <CloseIcon className="h-2.5 w-2.5" />
        </button>
      )}
    </div>
  );
}
