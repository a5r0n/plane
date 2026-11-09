/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useMember } from "@/hooks/store/use-member";
import { formatValue } from "../helpers";
import type { TProperty, TValue } from "../types";
import { BooleanEditor } from "./boolean-editor";
import { ChoiceEditor } from "./choice-editor";
import { DateEditor } from "./date-editor";
import { InlineInput } from "./inline-input";
import { MemberEditor } from "./member-editor";

type Props = {
  prop: TProperty;
  value: TValue;
  disabled: boolean;
  projectId: string;
  onChange: (value: TValue) => void;
};

/** One property's value: an editor by type, or plain text when the viewer can't write it. */
export const PropertyValueEditor = observer(function PropertyValueEditor(props: Props) {
  const { prop, value, disabled, projectId, onChange } = props;
  const { getUserDetails } = useMember();

  if (disabled) {
    const text = formatValue(prop, value, (id) => getUserDetails(id)?.display_name ?? "Unknown member");
    return (
      <span className={`block h-7.5 truncate px-2 text-13 leading-7.5 ${text ? "" : "text-placeholder"}`}>
        {text ?? "None"}
      </span>
    );
  }

  switch (prop.type) {
    case "boolean":
      return <BooleanEditor prop={prop} value={value} onChange={onChange} />;
    case "date":
    case "datetime":
      return <DateEditor prop={prop} value={value} onChange={onChange} />;
    case "choice":
      return <ChoiceEditor prop={prop} value={value} onChange={onChange} />;
    case "member":
      return <MemberEditor prop={prop} value={value} projectId={projectId} onChange={onChange} />;
    default:
      return <InlineInput prop={prop} value={value} onChange={onChange} />;
  }
});
