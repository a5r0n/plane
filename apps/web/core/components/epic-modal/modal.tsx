/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@plane/propel/button";
import { Dialog, DialogPanel } from "@plane/propel/dialog";
import { EIssueServiceType } from "@plane/types";
import type { TIssue } from "@plane/types";
import { IssueService } from "@/services/issue/issue.service"; // squadron

export interface EpicModalProps {
  data?: Partial<TIssue>;
  isOpen: boolean;
  onClose: () => void;
  beforeFormSubmit?: () => Promise<void>;
  onSubmit?: (res: TIssue) => Promise<void>;
  fetchIssueDetails?: boolean;
  primaryButtonText?: {
    default: string;
    loading: string;
  };
  isProjectSelectionDisabled?: boolean;
}

const epicService = new IssueService(EIssueServiceType.EPICS);

// squadron: minimal create form (name only).
export function CreateUpdateEpicModal(props: EpicModalProps) {
  const { data, isOpen, onClose, beforeFormSubmit, onSubmit } = props;
  const { workspaceSlug, projectId: routeProjectId } = useParams();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const projectId = data?.project_id ?? routeProjectId?.toString();

  const submit = async () => {
    if (!workspaceSlug || !projectId || !name.trim()) return;
    setLoading(true);
    try {
      await beforeFormSubmit?.();
      const res = await epicService.createIssue(workspaceSlug.toString(), projectId, { ...data, name: name.trim() });
      await onSubmit?.(res);
      setName("");
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogPanel>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-16 font-medium">Create epic</h3>
          <input
            className="w-full rounded-sm border border-subtle px-3 py-2 text-14"
            placeholder="Epic title"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void submit()}
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="lg" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="lg"
              type="button"
              disabled={loading || !name.trim()}
              onClick={() => void submit()}
            >
              {loading ? "Creating..." : "Create epic"}
            </Button>
          </div>
        </div>
      </DialogPanel>
    </Dialog>
  );
}
