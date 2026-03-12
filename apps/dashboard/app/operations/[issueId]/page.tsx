import { OperationsWorkbench } from "@/components/dashboard/operations-workbench";

export const dynamic = "force-dynamic";

export default async function OperationIssuePage({
  params,
}: {
  params: Promise<{ issueId: string }>;
}) {
  const { issueId } = await params;
  return <OperationsWorkbench initialIssueId={issueId} />;
}
