-- Create leads table in ai-memory database
-- This matches the schema defined in shared/schema.ts

CREATE TABLE IF NOT EXISTS leads (
  id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR NOT NULL,
  company VARCHAR NOT NULL,
  phone VARCHAR NOT NULL,
  email VARCHAR NOT NULL,
  source VARCHAR NOT NULL,
  current_stage VARCHAR NOT NULL DEFAULT 'first_contact',
  completed_milestones TEXT[] DEFAULT '{}',
  milestone_history JSONB DEFAULT '[]',
  notes TEXT DEFAULT '',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  stage_entered_at TIMESTAMP DEFAULT NOW()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_leads_current_stage ON leads(current_stage);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at DESC);

-- Show table structure
\d leads

-- Count records
SELECT COUNT(*) as total_leads FROM leads;
