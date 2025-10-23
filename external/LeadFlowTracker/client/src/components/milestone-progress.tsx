import { Check } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import type { Lead, LeadStage } from "@shared/schema";
import { leadStages } from "@shared/schema";

type MilestoneProgressProps = {
  lead: Lead;
  onMilestoneToggle: (milestone: LeadStage) => void;
};

const progressMilestones = leadStages.filter(s => s !== "Lost");

export function MilestoneProgress({ lead, onMilestoneToggle }: MilestoneProgressProps) {
  const completedMilestones = lead.completedMilestones || [];
  const isLost = lead.currentStage === "Lost";
  const currentStageIndex = isLost ? -1 : progressMilestones.indexOf(lead.currentStage as Exclude<LeadStage, "Lost">);
  
  const progressPercentage = isLost 
    ? 0 
    : ((completedMilestones.length) / (progressMilestones.length - 1)) * 100;

  const isMilestoneCompleted = (milestone: LeadStage) => {
    return completedMilestones.includes(milestone);
  };

  const canToggleMilestone = (milestone: LeadStage, index: number) => {
    if (isLost) return false;
    if (lead.currentStage === "Closed/Bound") return false;
    
    if (index === 0) return true;
    return isMilestoneCompleted(progressMilestones[index - 1]);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Progress value={progressPercentage} className="h-1.5 flex-1" />
        <span className="font-mono text-sm text-muted-foreground whitespace-nowrap" data-testid="text-progress-percentage">
          {Math.round(progressPercentage)}%
        </span>
      </div>
      
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {progressMilestones.map((milestone, index) => {
          const isCompleted = isMilestoneCompleted(milestone);
          const isCurrentStage = milestone === lead.currentStage;
          const canToggle = canToggleMilestone(milestone, index);

          return (
            <div
              key={milestone}
              className="flex items-center gap-2 min-w-fit"
            >
              <div className="flex items-center gap-1.5">
                <Checkbox
                  checked={isCompleted}
                  disabled={!canToggle}
                  onCheckedChange={() => canToggle && onMilestoneToggle(milestone)}
                  className="h-4 w-4"
                  data-testid={`checkbox-milestone-${milestone.toLowerCase().replace(/\s+/g, '-').replace('/', '-')}`}
                />
                <span
                  className={`text-xs font-medium whitespace-nowrap ${
                    isCompleted
                      ? "text-foreground"
                      : isCurrentStage
                      ? "text-primary"
                      : "text-muted-foreground"
                  }`}
                >
                  {milestone}
                </span>
              </div>
              {index < progressMilestones.length - 1 && (
                <div className="h-px w-4 bg-border" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
