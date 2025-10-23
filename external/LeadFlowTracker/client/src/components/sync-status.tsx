import { Check, Loader2, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

type SyncStatusProps = {
  status: "synced" | "syncing" | "error";
};

export function SyncStatus({ status }: SyncStatusProps) {
  if (status === "synced") {
    return (
      <Badge variant="outline" className="gap-1.5 border-chart-2/30 bg-chart-2/10 text-chart-2" data-testid="badge-sync-synced">
        <div className="h-1.5 w-1.5 rounded-full bg-chart-2" />
        Synced
        <Check className="h-3 w-3" />
      </Badge>
    );
  }

  if (status === "syncing") {
    return (
      <Badge variant="outline" className="gap-1.5 border-chart-3/30 bg-chart-3/10 text-chart-3" data-testid="badge-sync-syncing">
        <Loader2 className="h-3 w-3 animate-spin" />
        Syncing...
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="gap-1.5 border-destructive/30 bg-destructive/10 text-destructive" data-testid="badge-sync-error">
      <AlertCircle className="h-3 w-3" />
      Sync Error
    </Badge>
  );
}
