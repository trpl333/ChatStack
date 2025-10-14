# Notion Customer Database Integration

## 🎯 Overview

NeuroSphere Voice platform customers are now automatically saved to **both PostgreSQL and Notion**. This gives you:

✅ **Visual Management** - View/edit customers in Notion's beautiful interface  
✅ **Easy Access** - No command-line needed  
✅ **Automatic Sync** - Every signup automatically creates a Notion entry  
✅ **Backup** - Data stored in two places for redundancy

## 📊 Notion Database Structure

**Database Name:** `NeuroSphere Voice Customers`

### Fields:
- **Business Name** (Title) - Agency/company name
- **Contact Name** - Primary contact person
- **Email** - Login email (unique)
- **Phone** - Contact phone number
- **Package Tier** - Starter/Professional/Enterprise
- **Status** - Active/Trial/Suspended/Cancelled
- **Agent Name** - Their AI agent's name
- **Voice Type** - OpenAI voice (alloy, echo, fable, onyx, nova, shimmer)
- **Twilio Number** - Their dedicated phone number
- **Personality Preset** - AI personality setting
- **Greeting Template** - Custom greeting message
- **Created Date** - When they signed up
- **Last Login** - Last login timestamp
- **Notes** - Internal notes

## 🚀 Deployment Instructions

**On your DigitalOcean server:**

```bash
cd /opt/ChatStack

# Pull latest code with Notion integration
git pull origin main

# Deploy the changes
chmod +x deploy_notion_customer_db.sh
./deploy_notion_customer_db.sh
```

The script will:
1. Restart the Notion service with new schema
2. Create the "NeuroSphere Voice Customers" database
3. Restart Flask to enable the integration
4. Verify everything is working

## 🔍 Viewing Customers

### Option 1: Notion (Recommended)
1. Open your Notion workspace
2. Find the **"NeuroSphere Voice Customers"** database
3. View, search, filter, and edit customers visually

### Option 2: PostgreSQL (Technical)
```bash
docker exec -it chatstack-web-1 psql $DATABASE_URL -c \
  "SELECT id, email, business_name, package_tier, status FROM customers;"
```

## 🔄 How It Works

1. **Customer Signs Up** → `https://neurospherevoice.com/onboarding.html`
2. **Flask Saves to PostgreSQL** → Primary database
3. **Flask Calls Notion API** → `POST http://localhost:8200/notion/platform-customer`
4. **Notion Service Creates Entry** → Visible in Notion immediately
5. **Customer Can Login** → Uses PostgreSQL for authentication

## 📝 Managing Customers

### In Notion:
- ✏️ Edit any field directly
- 🏷️ Filter by status, package tier
- 📊 Create views (active customers, by tier, etc.)
- 📝 Add notes and track interactions
- 🔗 Link to other Notion pages

### In Code:
- Login/authentication uses PostgreSQL
- Dashboard settings use PostgreSQL
- Notion is for **viewing and management** only

## 🔧 API Endpoints

### Create/Update Platform Customer
```bash
POST http://localhost:8200/notion/platform-customer
Content-Type: application/json

{
  "email": "john@agency.com",
  "business_name": "ABC Insurance Agency",
  "contact_name": "John Smith",
  "phone": "555-1234",
  "package_tier": "Professional",
  "agent_name": "Sarah",
  "openai_voice": "nova",
  "personality_preset": "friendly",
  "greeting_template": "Hi, this is {agent_name}...",
  "status": "Active"
}
```

### Check Notion Health
```bash
GET http://localhost:8200/health
```

### List Databases
```bash
GET http://localhost:8200/notion/databases
```

## 🎯 Separation of Concerns

**NeuroSphere Voice Platform Customers** (database: `platform_customers`)
- Agencies that **purchase** the NeuroSphere Voice platform
- Stored in: PostgreSQL + Notion
- Example: "ABC Insurance Agency" buys the service

**Insurance Customers** (database: `customers`)  
- Clients of **The Insurance Doctors** who call the AI
- Stored in: Notion only (from phone calls)
- Example: "John Smith" calls about auto insurance

## 🛡️ Notes

- PostgreSQL is the **source of truth** for authentication
- Notion sync failures are **non-critical** (logged but don't break onboarding)
- Password hashes are **never** sent to Notion (security)
- Notion is for **viewing and management**, not authentication
