import { Button } from "@/components/ui/button";

type FilterTabsProps = {
  activeFilter: string;
  onFilterChange: (filter: string) => void;
  counts: {
    all: number;
    active: number;
    closed: number;
    lost: number;
  };
};

export function FilterTabs({ activeFilter, onFilterChange, counts }: FilterTabsProps) {
  const filters = [
    { id: "all", label: "All Leads", count: counts.all },
    { id: "active", label: "Active", count: counts.active },
    { id: "closed", label: "Closed/Bound", count: counts.closed },
    { id: "lost", label: "Lost", count: counts.lost },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {filters.map((filter) => (
        <Button
          key={filter.id}
          variant={activeFilter === filter.id ? "default" : "outline"}
          size="sm"
          onClick={() => onFilterChange(filter.id)}
          className="gap-2"
          data-testid={`button-filter-${filter.id}`}
        >
          {filter.label}
          <span className={`font-mono text-xs ${
            activeFilter === filter.id ? "opacity-90" : "opacity-70"
          }`}>
            {filter.count}
          </span>
        </Button>
      ))}
    </div>
  );
}
