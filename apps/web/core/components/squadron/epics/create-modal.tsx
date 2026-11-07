/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { EIssuesStoreType } from "@plane/types";
import { CreateUpdateEpicModal } from "@/components/epic-modal/modal";
import { useIssues } from "@/hooks/store/use-issues";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

// Name-only epic create that refreshes the epics list after it saves.
export const CreateEpicModal = observer(function CreateEpicModal({ isOpen, onClose }: Props) {
  const { workspaceSlug, projectId } = useParams();
  const { issues } = useIssues(EIssuesStoreType.EPIC);

  return (
    <CreateUpdateEpicModal
      isOpen={isOpen}
      onClose={onClose}
      onSubmit={async () => {
        if (workspaceSlug && projectId)
          await issues.fetchIssuesWithExistingPagination(workspaceSlug.toString(), projectId.toString(), "mutation");
      }}
    />
  );
});
