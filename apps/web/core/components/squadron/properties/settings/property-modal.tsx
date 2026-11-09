/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { isEqual } from "lodash-es";
import { observer } from "mobx-react";
import { Button } from "@plane/propel/button";
import { CustomSelect, EModalPosition, EModalWidth, Input, ModalCore, TextArea, ToggleSwitch } from "@plane/ui";
import { errorText, slugKey } from "../helpers";
import { PROPERTY_ICONS } from "../icons";
import type { TOption, TProperty, TPropertyInput, TPropertyType, TWriteRole } from "../types";
import { useProperties } from "../use-properties";
import { OptionsEditor } from "./options-editor";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  projectId: string;
  property?: TProperty;
};

export const TYPE_LABELS: Record<TPropertyType, string> = {
  text: "Text",
  number: "Number",
  boolean: "Yes / No",
  date: "Date",
  datetime: "Date & time",
  choice: "Choice",
  member: "Member",
  url: "URL",
};

const ROLE_LABELS: Record<TWriteRole, string> = { 20: "Admins", 15: "Members", 5: "Guests" };

type TForm = Required<Omit<TPropertyInput, "sort_order">>;

const EDITABLE = ["name", "description", "options", "multiple", "visible", "write_role"] as const;

const initial = (property?: TProperty): TForm => ({
  name: property?.name ?? "",
  key: property?.key ?? "",
  type: property?.type ?? "text",
  description: property?.description ?? "",
  options: property?.options ?? [],
  multiple: property?.multiple ?? false,
  visible: property?.visible ?? true,
  write_role: property?.write_role ?? 15,
});

// The fields the server gets: everything on create, only what changed on edit.
const payload = (form: TForm, property?: TProperty): TPropertyInput => {
  const withOptions = form.type === "choice";
  const withMultiple = form.type === "choice" || form.type === "member";
  if (!property) {
    const { options, multiple, ...rest } = form;
    return { ...rest, ...(withOptions && { options }), ...(withMultiple && { multiple }) };
  }
  const changed: TPropertyInput = {};
  for (const field of EDITABLE) {
    if (!isEqual(form[field], property[field])) Object.assign(changed, { [field]: form[field] });
  }
  if (!withOptions) delete changed.options;
  if (!withMultiple) delete changed.multiple;
  return changed;
};

function Field({ id, label, note, children }: { id?: string; label: string; note?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-13 font-medium text-secondary">
        {label}
      </label>
      {children}
      {note && <p className="text-12 text-tertiary">{note}</p>}
    </div>
  );
}

function Toggle({
  label,
  note,
  value,
  onChange,
}: {
  label: string;
  note: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-13 font-medium text-secondary">{label}</p>
        <p className="text-12 text-tertiary">{note}</p>
      </div>
      <ToggleSwitch value={value} label={label} onChange={onChange} />
    </div>
  );
}

/** Create or edit one property definition. Key and type are fixed once created. */
export const PropertyModal = observer(function PropertyModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, projectId, property } = props;
  const store = useProperties();
  const [form, setForm] = useState<TForm>(() => initial(property));
  const [keyEdited, setKeyEdited] = useState(false);
  const [error, setError] = useState<{ text: string; options: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const editing = !!property;

  useEffect(() => {
    if (!isOpen) return;
    setForm(initial(property));
    setKeyEdited(false);
    setError(null);
  }, [isOpen, property]);

  const set = <K extends keyof TForm>(field: K, value: TForm[K]) => setForm((f) => ({ ...f, [field]: value }));

  const setName = (name: string) =>
    setForm((f) => ({ ...f, name, ...(!editing && !keyEdited && { key: slugKey(name) }) }));

  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    const data = payload(form, property);
    if (editing && Object.keys(data).length === 0) return onClose();
    setSaving(true);
    setError(null);
    try {
      const ref = { slug: workspaceSlug, projectId };
      if (property) await store.updateDefinition(ref, property.id, data);
      else await store.createDefinition(ref, data);
      onClose();
    } catch (err) {
      const options = !!err && typeof err === "object" && "options" in err;
      setError({ text: errorText(err), options });
    } finally {
      setSaving(false);
    }
  };

  const TypeIcon = PROPERTY_ICONS[form.type];

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.TOP} width={EModalWidth.XXL}>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4 p-5">
        <h3 className="text-18 font-medium text-primary">{editing ? "Edit property" : "Add property"}</h3>
        <Field id="property-name" label="Name">
          <Input id="property-name" value={form.name} onChange={(e) => setName(e.target.value)} className="w-full" />
        </Field>
        <Field id="property-key" label="Key" note={editing ? "Keys never change; PQL and the API use them" : undefined}>
          <Input
            id="property-key"
            value={form.key}
            disabled={editing}
            className="font-mono w-full"
            onChange={(e) => {
              setKeyEdited(true);
              set("key", e.target.value);
            }}
          />
        </Field>
        {editing ? (
          <Field id="property-type" label="Type">
            <Input id="property-type" value={TYPE_LABELS[form.type]} disabled className="w-full" />
          </Field>
        ) : (
          <Field label="Type">
            <CustomSelect
              value={form.type}
              label={
                <span className="flex items-center gap-2">
                  <TypeIcon className="size-3.5" />
                  {TYPE_LABELS[form.type]}
                </span>
              }
              onChange={(type: TPropertyType) => set("type", type)}
              input
            >
              {(Object.keys(TYPE_LABELS) as TPropertyType[]).map((type) => {
                const Icon = PROPERTY_ICONS[type];
                return (
                  <CustomSelect.Option key={type} value={type}>
                    <span className="flex items-center gap-2">
                      <Icon className="size-3.5" />
                      {TYPE_LABELS[type]}
                    </span>
                  </CustomSelect.Option>
                );
              })}
            </CustomSelect>
          </Field>
        )}
        <Field id="property-description" label="Description (optional)">
          <TextArea
            id="property-description"
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
            className="w-full"
          />
        </Field>
        {form.type === "choice" && (
          <OptionsEditor
            options={form.options as TOption[]}
            error={error?.options ? error.text : undefined}
            onChange={(options) => set("options", options)}
          />
        )}
        {(form.type === "choice" || form.type === "member") && (
          <Toggle
            label="Allow multiple"
            note={
              form.type === "choice" ? "Pick more than one option per item." : "Pick more than one member per item."
            }
            value={form.multiple}
            onChange={(v) => set("multiple", v)}
          />
        )}
        <Toggle
          label="Show on work items"
          note="Off hides it in the web app; the API still returns it."
          value={form.visible}
          onChange={(v) => set("visible", v)}
        />
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-13 font-medium text-secondary">Who can set values</p>
            <p className="text-12 text-tertiary">Lowest project role that can change a value.</p>
          </div>
          <CustomSelect
            value={form.write_role}
            label={ROLE_LABELS[form.write_role]}
            onChange={(role: TWriteRole) => set("write_role", role)}
            input
          >
            {([20, 15, 5] as TWriteRole[]).map((role) => (
              <CustomSelect.Option key={role} value={role}>
                {ROLE_LABELS[role]}
              </CustomSelect.Option>
            ))}
          </CustomSelect>
        </div>
        {error && !error.options && <p className="text-12 text-danger-primary">{error.text}</p>}
        <div className="flex justify-end gap-2 border-t border-subtle pt-4">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" type="submit" loading={saving} disabled={!form.name.trim() || saving}>
            {editing ? "Save" : "Create"}
          </Button>
        </div>
      </form>
    </ModalCore>
  );
});
