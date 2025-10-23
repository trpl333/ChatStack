import { Users, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type EmptyStateProps = {
  onAddLead: () => void;
};

export function EmptyState({ onAddLead }: EmptyStateProps) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center p-12 text-center">
        <div className="rounded-full bg-muted p-6 mb-6">
          <Users className="h-12 w-12 text-muted-foreground" />
        </div>
        <h3 className="text-xl font-semibold mb-2">No leads yet</h3>
        <p className="text-muted-foreground mb-6 max-w-sm">
          Start tracking your first lead to see the pipeline in action. Add lead details and watch them progress through each stage.
        </p>
        <Button onClick={onAddLead} className="gap-2" data-testid="button-add-first-lead">
          <Plus className="h-4 w-4" />
          Add Your First Lead
        </Button>
      </CardContent>
    </Card>
  );
}
