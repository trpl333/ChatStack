import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, Clock, Target } from "lucide-react";
import type { Lead } from "@shared/schema";
import { differenceInDays } from "date-fns";

type AnalyticsSectionProps = {
  leads: Lead[];
};

export function AnalyticsSection({ leads }: AnalyticsSectionProps) {
  const closedLeads = leads.filter(l => l.currentStage === "Closed/Bound");
  const lostLeads = leads.filter(l => l.currentStage === "Lost");
  const activeLeads = leads.filter(l => l.currentStage !== "Closed/Bound" && l.currentStage !== "Lost");

  const avgDaysToClose = closedLeads.length > 0
    ? Math.round(
        closedLeads.reduce((sum, lead) => {
          const closedMilestone = lead.milestoneHistory?.find(h => h.stage === "Closed/Bound");
          const endDate = closedMilestone 
            ? new Date(closedMilestone.completedAt)
            : new Date(lead.updatedAt);
          const days = differenceInDays(endDate, new Date(lead.createdAt));
          return sum + days;
        }, 0) / closedLeads.length
      )
    : 0;

  const stageDurations = leads.reduce((acc, lead) => {
    if (!lead.milestoneHistory || lead.milestoneHistory.length === 0) return acc;

    const sortedHistory = [...lead.milestoneHistory].sort(
      (a, b) => new Date(a.completedAt).getTime() - new Date(b.completedAt).getTime()
    );

    sortedHistory.forEach((entry, index) => {
      const current = new Date(entry.completedAt);
      const previous = index > 0 
        ? new Date(sortedHistory[index - 1].completedAt)
        : new Date(lead.createdAt);
      
      const days = differenceInDays(current, previous);
      
      if (!acc[entry.stage]) {
        acc[entry.stage] = { totalDays: 0, count: 0 };
      }
      acc[entry.stage].totalDays += days;
      acc[entry.stage].count += 1;
    });

    return acc;
  }, {} as Record<string, { totalDays: number; count: number }>);

  const avgStageDurations = Object.entries(stageDurations).map(([stage, data]) => ({
    stage,
    avgDays: Math.round(data.totalDays / data.count),
  }));

  const conversionRate = closedLeads.length + lostLeads.length > 0
    ? ((closedLeads.length / (closedLeads.length + lostLeads.length)) * 100).toFixed(1)
    : "0";

  const activePipelineValue = activeLeads.length;

  return (
    <div className="space-y-4" data-testid="analytics-section">
      <h2 className="text-lg font-semibold">Pipeline Analytics</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card data-testid="card-avg-days-to-close">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Clock className="h-4 w-4 text-primary" />
              Avg. Days to Close
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold" data-testid="text-avg-days">
              {avgDaysToClose}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Based on {closedLeads.length} closed {closedLeads.length === 1 ? "lead" : "leads"}
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-conversion-funnel">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Target className="h-4 w-4 text-primary" />
              Win Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold" data-testid="text-win-rate">
              {conversionRate}%
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {closedLeads.length} won, {lostLeads.length} lost
            </p>
          </CardContent>
        </Card>

        <Card data-testid="card-active-pipeline">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              Active Pipeline
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold" data-testid="text-active-count">
              {activePipelineValue}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Leads in progress
            </p>
          </CardContent>
        </Card>
      </div>

      {avgStageDurations.length > 0 && (
        <Card data-testid="card-stage-durations">
          <CardHeader>
            <CardTitle className="text-sm font-medium">Average Time in Each Stage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {avgStageDurations
                .sort((a, b) => b.avgDays - a.avgDays)
                .map(({ stage, avgDays }) => (
                  <div key={stage} className="flex items-center justify-between" data-testid={`stage-duration-${stage}`}>
                    <span className="text-sm font-medium">{stage}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-primary rounded-full"
                          style={{ 
                            width: `${Math.min((avgDays / Math.max(...avgStageDurations.map(s => s.avgDays), 1)) * 100, 100)}%` 
                          }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground font-mono w-12 text-right">
                        {avgDays}d
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
