# Sales Lead Tracker

A professional daily tracker for insurance sales teams that automatically syncs with Google Sheets. Track leads from first contact through to closed/bound or lost with milestone progression and real-time updates.

## Overview

This application helps insurance agencies track their sales pipeline with:
- **Lead Management**: Add and track leads with contact information
- **Stage Progression**: Visual milestone system with checkboxes that auto-advance leads
- **Google Sheets Sync**: Automatic synchronization to Google Sheets for backup and sharing
- **Analytics Dashboard**: Real-time stats on pipeline, conversion rates, and lead status
- **Dark Mode**: Professional dark theme optimized for daily use

## Features

### Lead Lifecycle
Leads progress through seven stages:
1. **First Contact** - Initial outreach
2. **Follow-up** - Subsequent communication
3. **Quote Sent** - Proposal delivered
4. **Application** - Paperwork submitted
5. **Underwriting** - In review
6. **Closed/Bound** - Successfully won
7. **Lost** - Opportunity lost (can be reactivated)

### Dashboard
- **Stats Cards**: Total leads, active pipeline, closed/bound count, conversion rate
- **Filter Tabs**: View all leads, active only, closed, or lost
- **Lead Cards**: Expandable cards showing contact details, source, and progress
- **Milestone Progress**: Interactive checkboxes with visual progress bar
- **Sync Status**: Real-time indicator of Google Sheets synchronization

### Actions
- **Add Lead**: Form with validation for name, company, phone, email, and source
- **Toggle Milestones**: Check/uncheck to advance or regress stages
- **Mark as Lost**: Move any active lead to lost status
- **Reactivate**: Restore lost leads to their previous position in the pipeline

## Technical Architecture

### Frontend
- **React** with TypeScript for type safety
- **Wouter** for lightweight routing
- **TanStack Query** for server state management
- **Shadcn UI** components with Tailwind CSS
- **Date-fns** for time calculations
- **Zod** for form validation

### Backend
- **Express.js** API server
- **In-memory storage** for fast prototyping
- **Google Sheets API** via Replit connector
- **Automatic sync** on all lead operations

### Data Model
```typescript
type Lead = {
  id: string;
  name: string;
  company: string;
  phone: string;
  email: string;
  source: string;
  currentStage: LeadStage;
  completedMilestones: string[];
  notes: string;
  createdAt: Date;
  updatedAt: Date;
  stageEnteredAt: Date;
}
```

## API Endpoints

- `GET /api/leads` - Fetch all leads
- `POST /api/leads` - Create new lead
- `GET /api/leads/:id` - Get specific lead
- `POST /api/leads/:id/milestone` - Toggle milestone completion
- `POST /api/leads/:id/mark-lost` - Mark lead as lost
- `POST /api/leads/:id/reactivate` - Reactivate lost lead

## Google Sheets Integration

The application automatically:
1. Creates a new spreadsheet titled "Sales Lead Tracker" on first use
2. Sets up headers with proper formatting
3. Syncs every lead creation and update
4. Maintains complete history in the sheet

Sheet columns: ID, Name, Company, Phone, Email, Source, Current Stage, Completed Milestones, Notes, Created At, Updated At, Stage Entered At

## Design System

Following a productivity-focused design inspired by Linear and Notion:
- **Colors**: Trust-inspiring blue primary, green for success, red for lost
- **Typography**: Inter for UI, JetBrains Mono for data/metrics
- **Spacing**: Consistent 4px base unit
- **Interactions**: Subtle hover states, minimal animations
- **Dark Mode**: Default dark theme with light mode toggle

## User Preferences

- Default theme: Dark mode
- Empty state onboarding for new users
- Responsive design for mobile and desktop
- Keyboard navigation support

## Deployment Architecture

### Development Environment (Replit)
- **Database**: Replit PostgreSQL (Neon)
- **URL**: Replit workspace preview
- **Purpose**: Development and testing
- **Google Sheets**: Automatic backup sync

### Production Environment (DigitalOcean)
- **Database**: DigitalOcean ai-memory PostgreSQL (shared with ChatStack/NeuroSphere)
- **URL**: https://leads.theinsurancedoctors.com
- **GitHub**: https://github.com/trpl333/LeadFlowTracker
- **Server**: Same droplet as ChatStack (209.38.143.71)
- **Process Manager**: PM2
- **Reverse Proxy**: Nginx with SSL (Let's Encrypt)

### Deployment Workflow
```
Replit → GitHub → DigitalOcean
   ↓         ↓          ↓
Replit DB  Code     ai-memory DB
           Repo     (Production)
```

**To deploy changes:**
1. Make changes in Replit workspace
2. Commit and push to GitHub: `git push origin main`
3. SSH to DigitalOcean: `ssh root@209.38.143.71`
4. Navigate to project: `cd /opt/LeadFlowTracker`
5. Run deploy script: `./deploy.sh`

Or manually:
```bash
git pull origin main
npm install
npm run build
npm run db:push
pm2 restart leadflow-tracker
```

## Integration with ai-memory Ecosystem

The Lead Tracker integrates with the existing NeuroSphere AI ecosystem:

- **Shared Database**: Uses DigitalOcean ai-memory PostgreSQL in production
- **ChatStack Access**: AI phone system can query lead data for context
- **Notion Integration**: Lead data can be synced to Notion via ai-memory
- **Data Consistency**: All systems share the same source of truth

### Database Tables in ai-memory
- `leads` - Lead tracker data (this app)
- `users` - Authentication (shared)
- Other tables used by ChatStack/NeuroSphere

## Recent Changes

**2025-10-21**: Production deployment setup
- GitHub repository created and connected
- DigitalOcean deployment configuration
- Environment-aware database connection
- PM2 process management setup
- Nginx reverse proxy configuration
- SSL certificate setup for custom domain

**2025-10-20**: Initial implementation
- Complete lead tracking system
- PostgreSQL database with Drizzle ORM
- Google Sheets integration
- Dashboard with analytics
- Filter and search functionality
- Dark mode with theme toggle
- Milestone progression system
- Mark as lost/reactivate functionality
- Bulk actions system
- Editable notes with history
- Stage date tracking

## Development

The app runs on port 5000 with hot reload enabled:
- Frontend: Vite dev server
- Backend: Express with tsx for TypeScript
- Database: Replit PostgreSQL (development) or DigitalOcean (production)
- Google Sheets: Connected via Replit integration

## Future Enhancements

Potential improvements:
- Date tracking for each milestone transition
- Email/SMS notifications for overdue leads
- Bulk actions for multiple leads
- Advanced filtering by date range or source
- Export functionality
- Custom fields per lead
- Team collaboration features
