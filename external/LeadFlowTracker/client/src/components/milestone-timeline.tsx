import { CheckCircle2, Clock } from "lucide-react";
import { formatDistanceToNow, differenceInDays } from "date-fns";
import type { MilestoneHistory, LeadStage } from "@shared/schema";

type MilestoneTimelineProps = {
  milestoneHistory: MilestoneHistory;
  currentStage: LeadStage;
};

export function MilestoneTimeline({ milestoneHistory, currentStage }: MilestoneTimelineProps) {
  if (!milestoneHistory || milestoneHistory.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        No milestone history yet
      </div>
    );
  }

  const sortedHistory = [...milestoneHistory].sort(
    (a, b) => new Date(a.completedAt).getTime() - new Date(b.completedAt).getTime()
  );

  const calculateDaysInStage = (index: number) => {
    const current = new Date(sortedHistory[index].completedAt);
    const previous = index > 0 ? new Date(sortedHistory[index - 1].completedAt) : null;
    
    if (previous) {
      return differenceInDays(current, previous);
    }
    return 0;
  };

  return (
    <div className="space-y-1" data-testid="milestone-timeline">
      {sortedHistory.map((entry, index) => {
        const daysInStage = calculateDaysInStage(index);
        
        return (
          <div
            key={`${entry.stage}-${entry.completedAt}`}
            className="flex items-start gap-3 py-2 border-l-2 border-muted pl-3"
            data-testid={`timeline-entry-${entry.stage}`}
          >
            <CheckCircle2 className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-medium text-sm">{entry.stage}</span>
                {daysInStage > 0 && (
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {daysInStage} {daysInStage === 1 ? "day" : "days"} in stage
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Completed {formatDistanceToNow(new Date(entry.completedAt), { addSuffix: true })}
              </p>
            </div>
          </div>
        );
      })}
      
      {currentStage !== "Closed/Bound" && currentStage !== "Lost" && (
        <div className="flex items-start gap-3 py-2 pl-3 opacity-60">
          <div className="h-4 w-4 rounded-full border-2 border-dashed border-muted-foreground shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <span className="font-medium text-sm text-muted-foreground">Currently in {currentStage}</span>
          </div>
        </div>
      )}
    </div>
  );
}
