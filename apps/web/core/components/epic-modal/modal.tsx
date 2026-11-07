/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { Dialog, DialogPanel } from "@plane/propel/dialog";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
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

// squadron: minimal name-only form; updates when data has an id.
export function CreateUpdateEpicModal(props: EpicModalProps) {
  const { data, isOpen, onClose, beforeFormSubmit, onSubmit } = props;
  const { t } = useTranslation();
  const { workspaceSlug, projectId: routeProjectId } = useParams();
  const [name, setName] = useState(data?.name ?? "");
  const [loading, setLoading] = useState(false);
  const projectId = data?.project_id ?? routeProjectId?.toString();
  const isUpdate = !!data?.id;

  useEffect(() => {
    if (isOpen) setName(data?.name ?? "");
  }, [isOpen, data?.name]);

  const submit = async () => {
    if (!workspaceSlug || !projectId || !name.trim()) return;
    setLoading(true);
    try {
      await beforeFormSubmit?.();
      const payload = { ...data, name: name.trim() };
      const res: TIssue = data?.id
        ? {
            ...(await epicService.patchIssue(workspaceSlug.toString(), projectId, data.id, { name: payload.name })),
            ...payload,
          }
        : await epicService.createIssue(workspaceSlug.toString(), projectId, payload);
      await onSubmit?.(res);
      setName("");
      onClose();
    } catch (error: any) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("common.error.label"),
        message: error?.error ?? t("common.error.message"),
      });
    } finally {
      setLoading(false);
    }
  };

  const title = isUpdate ? `${t("common.update")} ${t("common.epic")}` : t("project_empty_state.epics.cta_primary");

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogPanel>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-16 font-medium">{title}</h3>
          <input
            className="w-full rounded-sm border border-subtle px-3 py-2 text-14"
            placeholder={t("common.title")}
            aria-label={t("common.title")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void submit()}
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="lg" type="button" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="primary"
              size="lg"
              type="button"
              disabled={loading || !name.trim()}
              onClick={() => void submit()}
            >
              {isUpdate
                ? t(loading ? "common.updating" : "common.update")
                : t(loading ? "common.creating" : "common.create")}
            </Button>
          </div>
        </div>
      </DialogPanel>
    </Dialog>
  );
}
