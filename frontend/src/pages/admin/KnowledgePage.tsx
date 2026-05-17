import UploadZone from "../../components/admin/knowledge/UploadZone";
import DocumentTable from "../../components/admin/knowledge/DocumentTable";
import { useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "../../lib/constants";

export default function KnowledgePage() {
  const queryClient = useQueryClient();

  function handleUploadSuccess() {
    queryClient.invalidateQueries({ queryKey: QUERY_KEYS.knowledge.documents() });
  }

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-gray-900">知识库管理</h2>
      <UploadZone onSuccess={handleUploadSuccess} />
      <DocumentTable />
    </div>
  );
}
