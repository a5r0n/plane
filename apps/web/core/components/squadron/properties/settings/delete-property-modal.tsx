/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { AlertModalCore } from "@plane/ui";
import { errorText } from "../helpers";
import type { TProperty } from "../types";
import { useProperties } from "../use-properties";

type Props = { isOpen: boolean; onClose: () => void; workspaceSlug: string; projectId: string; property: TProperty };

/** Confirm before deleting a definition; its values stay stored and its key stays taken. */
export const DeletePropertyModal = observer(function DeletePropertyModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, projectId, property } = props;
  const store = useProperties();
  const [deleting, setDeleting] = useState(false);

  const submit = async () => {
    setDeleting(true);
    try {
      await store.removeDefinition({ slug: workspaceSlug, projectId }, property.id);
      onClose();
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: `Couldn't delete ${property.name}`, message: errorText(error) });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <AlertModalCore
      isOpen={isOpen}
      handleClose={onClose}
      handleSubmit={() => void submit()}
      isSubmitting={deleting}
      title={`Delete ${property.name}?`}
      content={
        <>
          Values stay stored but stop showing anywhere. The key <span className="font-mono">{property.key}</span>{" "}
          can&apos;t be reused.
        </>
      }
    />
  );
});
