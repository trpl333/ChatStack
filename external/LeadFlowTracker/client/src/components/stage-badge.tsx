import { Badge } from "@/components/ui/badge";
import { 
  PhoneCall, 
  MessageSquare, 
  FileText, 
  ClipboardCheck, 
  Clock, 
  CheckCircle2, 
  XCircle 
} from "lucide-react";
import type { LeadStage } from "@shared/schema";

type StageBadgeProps = {
  stage: LeadStage;
};

const stageConfig: Record<LeadStage, { icon: typeof PhoneCall; color: string; bgClass: string; borderClass: string; textClass: string }> = {
  "First Contact": {
    icon: PhoneCall,
    color: "primary",
    bgClass: "bg-primary/10",
    borderClass: "border-primary/30",
    textClass: "text-primary"
  },
  "Follow-up": {
    icon: MessageSquare,
    color: "chart-3",
    bgClass: "bg-chart-3/10",
    borderClass: "border-chart-3/30",
    textClass: "text-chart-3"
  },
  "Quote Sent": {
    icon: FileText,
    color: "accent",
    bgClass: "bg-accent",
    borderClass: "border-accent-border",
    textClass: "text-accent-foreground"
  },
  "Application": {
    icon: ClipboardCheck,
    color: "secondary",
    bgClass: "bg-secondary",
    borderClass: "border-secondary-border",
    textClass: "text-secondary-foreground"
  },
  "Underwriting": {
    icon: Clock,
    color: "muted",
    bgClass: "bg-muted",
    borderClass: "border-muted-border",
    textClass: "text-muted-foreground"
  },
  "Closed/Bound": {
    icon: CheckCircle2,
    color: "success",
    bgClass: "bg-chart-2/10",
    borderClass: "border-chart-2/30",
    textClass: "text-chart-2"
  },
  "Lost": {
    icon: XCircle,
    color: "destructive",
    bgClass: "bg-destructive/10",
    borderClass: "border-destructive/30",
    textClass: "text-destructive"
  }
};

export function StageBadge({ stage }: StageBadgeProps) {
  const config = stageConfig[stage];
  const Icon = config.icon;

  return (
    <Badge 
      variant="outline" 
      className={`gap-1.5 ${config.bgClass} ${config.borderClass} ${config.textClass}`}
      data-testid={`badge-stage-${stage.toLowerCase().replace(/\s+/g, '-').replace('/', '-')}`}
    >
      <Icon className="h-3 w-3" />
      {stage}
    </Badge>
  );
}
