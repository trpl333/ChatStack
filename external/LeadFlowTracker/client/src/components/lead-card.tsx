import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import { ChevronDown, ChevronUp, Mail, Phone, Building2, Flag, XCircle, RotateCcw } from "lucide-react";
import { StageBadge } from "./stage-badge";
import { MilestoneProgress } from "./milestone-progress";
import { MilestoneTimeline } from "./milestone-timeline";
import type { Lead, LeadStage } from "@shared/schema";
import { formatDistanceToNow } from "date-fns";
import { useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";

type LeadCardProps = {
  lead: Lead;
  onMilestoneToggle: (leadId: string, milestone: LeadStage) => void;
  onMarkAsLost: (leadId: string) => void;
  onReactivate: (leadId: string) => void;
  selected?: boolean;
  onToggleSelect?: (leadId: string) => void;
};

export function LeadCard({ lead, onMilestoneToggle, onMarkAsLost, onReactivate, selected, onToggleSelect }: LeadCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(lead.notes);
  const { toast } = useToast();
  
  useEffect(() => {
    setNotes(lead.notes);
  }, [lead.notes]);
  
  const daysInStage = Math.floor(
    (new Date().getTime() - new Date(lead.stageEnteredAt).getTime()) / (1000 * 60 * 60 * 24)
  );
  
  const isOverdue = daysInStage > 3 && lead.currentStage !== "Closed/Bound" && lead.currentStage !== "Lost";
  const isLost = lead.currentStage === "Lost";
  const isClosed = lead.currentStage === "Closed/Bound";
  const canMarkAsLost = !isLost && !isClosed;

  const updateNotesMutation = useMutation({
    mutationFn: async (newNotes: string) => {
      return await apiRequest("PATCH", `/api/leads/${lead.id}/notes`, { notes: newNotes });
    },
    onSuccess: (updatedLead) => {
      queryClient.invalidateQueries({ queryKey: ["/api/leads"] });
      setNotes(updatedLead.notes);
      toast({
        title: "Notes updated",
        description: "Lead notes have been saved.",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to update notes. Please try again.",
        variant: "destructive",
      });
    },
  });

  const handleNotesBlur = () => {
    if (notes !== lead.notes) {
      updateNotesMutation.mutate(notes);
    }
  };

  return (
    <Card className="hover-elevate" data-testid={`card-lead-${lead.id}`}>
      <CardContent className="p-4">
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              {onToggleSelect && (
                <Checkbox
                  checked={selected}
                  onCheckedChange={() => onToggleSelect(lead.id)}
                  data-testid={`checkbox-select-${lead.id}`}
                  className="shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-base truncate" data-testid={`text-lead-name-${lead.id}`}>
                    {lead.name}
                  </h3>
                  {isOverdue && (
                    <Badge variant="outline" className="gap-1 border-destructive/30 bg-destructive/10 text-destructive">
                      <Flag className="h-3 w-3" />
                      Overdue
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Building2 className="h-3.5 w-3.5" />
                  <span className="truncate" data-testid={`text-lead-company-${lead.id}`}>{lead.company}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StageBadge stage={lead.currentStage as LeadStage} />
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setExpanded(!expanded)}
                data-testid={`button-expand-${lead.id}`}
              >
                {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <span className="font-medium">Days in stage:</span>
              <span className="font-mono" data-testid={`text-days-in-stage-${lead.id}`}>{daysInStage}</span>
            </div>
            <div className="text-muted-foreground">
              Added {formatDistanceToNow(new Date(lead.createdAt), { addSuffix: true })}
            </div>
          </div>

          <MilestoneProgress
            lead={lead}
            onMilestoneToggle={(milestone) => onMilestoneToggle(lead.id, milestone)}
          />

          {!isLost && !isClosed && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onMarkAsLost(lead.id)}
                className="gap-1.5 text-destructive border-destructive/30 hover:bg-destructive/10"
                data-testid={`button-mark-lost-${lead.id}`}
              >
                <XCircle className="h-3.5 w-3.5" />
                Mark as Lost
              </Button>
            </div>
          )}

          {isLost && (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => onReactivate(lead.id)}
                className="gap-1.5"
                data-testid={`button-reactivate-${lead.id}`}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reactivate Lead
              </Button>
            </div>
          )}

          {expanded && (
            <div className="pt-4 border-t space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <a
                    href={`mailto:${lead.email}`}
                    className="text-primary hover:underline truncate"
                    data-testid={`link-email-${lead.id}`}
                  >
                    {lead.email}
                  </a>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Phone className="h-4 w-4 text-muted-foreground" />
                  <a
                    href={`tel:${lead.phone}`}
                    className="text-primary hover:underline"
                    data-testid={`link-phone-${lead.id}`}
                  >
                    {lead.phone}
                  </a>
                </div>
              </div>
              
              <div className="text-sm">
                <span className="text-muted-foreground">Source:</span>{" "}
                <span data-testid={`text-source-${lead.id}`}>{lead.source}</span>
              </div>
              
              <div className="space-y-2">
                <label htmlFor={`notes-${lead.id}`} className="text-sm text-muted-foreground">
                  Notes
                </label>
                <Textarea
                  id={`notes-${lead.id}`}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  onBlur={handleNotesBlur}
                  placeholder="Add call summaries, client details, or follow-up reminders..."
                  className="resize-none min-h-[80px]"
                  data-testid={`textarea-notes-${lead.id}`}
                />
              </div>

              <Separator />

              <div className="space-y-2">
                <h4 className="text-sm font-medium">Milestone History</h4>
                <MilestoneTimeline 
                  milestoneHistory={lead.milestoneHistory || []} 
                  currentStage={lead.currentStage as LeadStage}
                />
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
