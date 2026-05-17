import { useState } from "react";
import MetricsCards from "../../components/admin/logs/MetricsCards";
import LogTable from "../../components/admin/logs/LogTable";
import LogDetailDrawer from "../../components/admin/logs/LogDetailDrawer";
import type { LogItem } from "../../types/admin";

export default function LogsPage() {
  const [selectedLog, setSelectedLog] = useState<LogItem | null>(null);

  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-gray-900">问答日志</h2>
      <MetricsCards />
      <LogTable onSelect={setSelectedLog} />
      <LogDetailDrawer log={selectedLog} onClose={() => setSelectedLog(null)} />
    </div>
  );
}
