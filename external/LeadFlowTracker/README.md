# LeadFlowTracker

A professional daily sales lead tracker for insurance agencies with automatic Google Sheets synchronization.

![Status](https://img.shields.io/badge/status-production-green)
![Database](https://img.shields.io/badge/database-PostgreSQL-blue)

## 🚀 Live Production

**Production URL:** [leads.theinsurancedoctors.com](https://leads.theinsurancedoctors.com)

## 📋 Overview

LeadFlowTracker helps insurance sales teams track their pipeline from first contact through to closed/bound or lost status. Features real-time Google Sheets synchronization, milestone-based progression, and comprehensive analytics.

### Key Features

- **Lead Management** - Add and track leads with contact information
- **7-Stage Milestone System** - Visual progress tracking with checkboxes
- **Google Sheets Sync** - Automatic backup and sharing
- **Analytics Dashboard** - Real-time stats and conversion rates
- **Bulk Actions** - Efficiently manage multiple leads
- **Search & Filter** - Find leads by name, company, email, or source
- **Dark Mode** - Professional theme optimized for daily use
- **Notes System** - Track important details and updates
- **Stage History** - See when leads entered each stage

## 🛠️ Tech Stack

### Frontend
- **React** with TypeScript
- **Wouter** for routing
- **TanStack Query** for state management
- **Shadcn UI** + **Tailwind CSS** for styling
- **Zod** for form validation

### Backend
- **Express.js** API server
- **PostgreSQL** (Replit/Neon) for data persistence
- **Google Sheets API** via Replit connector
- **Drizzle ORM** for type-safe database queries

## 📊 Lead Lifecycle

Leads progress through seven stages:

1. **First Contact** - Initial outreach
2. **Follow-up** - Subsequent communication
3. **Quote Sent** - Proposal delivered
4. **Application** - Paperwork submitted
5. **Underwriting** - In review
6. **Closed/Bound** - Successfully won ✅
7. **Lost** - Opportunity lost (can be reactivated)

## 🔧 Development

### Prerequisites
- Node.js 20+
- PostgreSQL database
- Google Sheets API access (via Replit connector)

### Environment Variables
```bash
DATABASE_URL=postgresql://...
SESSION_SECRET=your-secret-key
```

### Installation
```bash
npm install
```

### Database Setup
```bash
# Push schema to database
npm run db:push

# Or force push if needed
npm run db:push --force
```

### Running Locally
```bash
npm run dev
```

The app will be available at `http://localhost:5000`

## 📁 Project Structure

```
├── client/               # Frontend React app
│   └── src/
│       ├── pages/        # Page components
│       ├── components/   # Reusable UI components
│       └── lib/          # Utilities and query client
├── server/               # Backend Express server
│   ├── routes.ts         # API endpoints
│   ├── storage.ts        # Database interface
│   └── db.ts            # Database connection
├── shared/
│   └── schema.ts         # Shared TypeScript types & Drizzle schema
└── integrations/         # Replit integrations (Google Sheets)
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/leads` | Fetch all leads |
| POST | `/api/leads` | Create new lead |
| GET | `/api/leads/:id` | Get specific lead |
| PATCH | `/api/leads/:id` | Update lead details |
| PATCH | `/api/leads/:id/stage` | Update lead stage |
| POST | `/api/leads/:id/milestone` | Toggle milestone |
| POST | `/api/leads/:id/mark-lost` | Mark lead as lost |
| POST | `/api/leads/:id/reactivate` | Reactivate lost lead |
| POST | `/api/leads/bulk-actions` | Perform bulk operations |

## 📈 Google Sheets Integration

The application automatically:
1. Creates a spreadsheet titled "Sales Lead Tracker" on first use
2. Sets up formatted headers
3. Syncs every lead creation and update
4. Maintains complete historical data

**Sheet Columns:** ID, Name, Company, Phone, Email, Source, Current Stage, Completed Milestones, Notes, Created At, Updated At, Stage Entered At

## 🎨 Design System

Inspired by Linear and Notion:
- **Colors:** Trust-inspiring blue primary, green for success
- **Typography:** Inter for UI, consistent sizing
- **Spacing:** 4px base unit
- **Dark Mode:** Default theme with professional contrast

## 🚀 Deployment

### Replit Publishing
1. Go to the Publishing panel in Replit
2. Click "Republish" to deploy changes
3. Custom domain configured via DNS (A + TXT records)

### Database
- **Development:** Replit PostgreSQL
- **Production:** Separate production database
- **Backup:** Google Sheets sync

## 🔄 Workflow

**Development → GitHub → Production**

1. Make changes in Replit workspace
2. Test thoroughly in development
3. Commit and push to GitHub
4. Click "Republish" in Replit Publishing panel
5. Changes go live at leads.theinsurancedoctors.com

## 📝 Future Enhancements

- Date tracking for each milestone transition
- Email/SMS notifications for overdue leads
- Advanced filtering by date range or source
- Export functionality (CSV, PDF)
- Custom fields per lead
- Team collaboration features
- Mobile app

## 📄 License

Proprietary - The Insurance Doctors

## 👥 Team

Built for insurance sales teams at The Insurance Doctors.

---

**Questions or Issues?** Check the [Issues](https://github.com/trpl333/LeadFlowTracker/issues) page or contact support.
