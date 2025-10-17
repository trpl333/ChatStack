/**
 * Notion Integration Service for Peterson Family Insurance
 * 
 * This service provides complete bi-directional sync between:
 * - Notion databases (CRM, policies, calls, tasks, calendar)
 * - AI-Memory service (customer context for AI agent)
 * 
 * Architecture:
 * - Phone Call → FastAPI → AI-Memory → Notion Sync → Notion
 * - Notion → Notion Sync → AI-Memory → AI Agent (during calls)
 */

import { Client } from '@notionhq/client';
import fetch from 'node-fetch';

// ============================================================================
// CONFIGURATION
// ============================================================================

const AI_MEMORY_URL = process.env.AI_MEMORY_URL || 'http://172.17.0.1:8100';

// Notion OAuth client (handles token refresh automatically)
let connectionSettings = null;

async function getAccessToken() {
  // Priority 1: Use direct NOTION_TOKEN if available (production mode)
  if (process.env.NOTION_TOKEN) {
    const token = process.env.NOTION_TOKEN.trim();
    console.log('✅ Using direct NOTION_TOKEN for authentication');
    return token;
  }
  
  // Priority 2: Use Replit OAuth connector (development mode)
  // Check if cached token is still valid
  if (connectionSettings?.settings?.expires_at) {
    const expiryTime = new Date(connectionSettings.settings.expires_at).getTime();
    if (expiryTime > Date.now()) {
      return connectionSettings.settings.access_token;
    }
  }
  
  // Try to fetch new token from Replit connector
  const hostname = process.env.REPLIT_CONNECTORS_HOSTNAME;
  const xReplitToken = process.env.REPL_IDENTITY 
    ? 'repl ' + process.env.REPL_IDENTITY 
    : process.env.WEB_REPL_RENEWAL 
    ? 'depl ' + process.env.WEB_REPL_RENEWAL 
    : null;

  if (!xReplitToken) {
    console.warn('⚠️ No NOTION_TOKEN or Replit OAuth credentials found');
    return null;
  }

  try {
    const response = await fetch(
      'https://' + hostname + '/api/v2/connection?include_secrets=true&connector_names=notion',
      {
        headers: {
          'Accept': 'application/json',
          'X_REPLIT_TOKEN': xReplitToken
        }
      }
    );
    
    const data = await response.json();
    connectionSettings = data.items?.[0];

    const accessToken = connectionSettings?.settings?.access_token || 
                       connectionSettings?.settings?.oauth?.credentials?.access_token;

    if (accessToken) {
      return accessToken;
    }
  } catch (error) {
    console.error('Failed to fetch Replit OAuth token:', error);
  }
  
  return null;
}

async function getNotionClient() {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    throw new Error('❌ No Notion authentication token available. Set NOTION_TOKEN in environment.');
  }
  return new Client({ auth: accessToken });
}

// ============================================================================
// NOTION DATABASE SCHEMAS
// ============================================================================

const DATABASE_SCHEMAS = {
  // NeuroSphere Voice Platform Customers (Agencies purchasing the platform)
  platform_customers: {
    name: 'NeuroSphere Voice Customers',
    properties: {
      'Business Name': { title: {} },
      'Contact Name': { rich_text: {} },
      'Email': { email: {} },
      'Phone': { phone_number: {} },
      'Package Tier': { 
        select: { 
          options: [
            { name: 'Starter', color: 'blue' },
            { name: 'Professional', color: 'purple' },
            { name: 'Enterprise', color: 'orange' }
          ] 
        } 
      },
      'Status': { 
        select: { 
          options: [
            { name: 'Active', color: 'green' },
            { name: 'Trial', color: 'yellow' },
            { name: 'Suspended', color: 'red' },
            { name: 'Cancelled', color: 'gray' }
          ] 
        } 
      },
      'Agent Name': { rich_text: {} },
      'Voice Type': { 
        select: { 
          options: [
            { name: 'alloy', color: 'gray' },
            { name: 'echo', color: 'blue' },
            { name: 'fable', color: 'purple' },
            { name: 'onyx', color: 'default' },
            { name: 'nova', color: 'pink' },
            { name: 'shimmer', color: 'yellow' }
          ] 
        } 
      },
      'Twilio Number': { phone_number: {} },
      'Personality Preset': { rich_text: {} },
      'Greeting Template': { rich_text: {} },
      'Created Date': { date: {} },
      'Last Login': { date: {} },
      'Notes': { rich_text: {} }
    }
  },

  // Customer Database (Insurance clients - for The Insurance Doctors)
  customers: {
    name: 'Insurance Customers',
    properties: {
      'Customer Name': { title: {} },
      'Phone': { phone_number: {} },
      'Email': { email: {} },
      'Address': { rich_text: {} },
      'Family Members': { rich_text: {} },
      'Spouse': { rich_text: {} },
      'Children': { rich_text: {} },
      'Policies': { relation: { database_id: 'policies' } },
      'Last Call': { date: {} },
      'Total Calls': { number: { format: 'number' } },
      'Notes': { rich_text: {} },
      'Tags': { multi_select: { options: [] } },
      'Status': { 
        select: { 
          options: [
            { name: 'Active', color: 'green' },
            { name: 'Inactive', color: 'gray' },
            { name: 'VIP', color: 'purple' }
          ] 
        } 
      }
    }
  },

  // Call Logs Database
  calls: {
    name: 'Call Logs',
    properties: {
      'Call Date': { date: {} },
      'Customer': { relation: { database_id: 'customers' } },
      'Phone Number': { phone_number: {} },
      'Call SID': { rich_text: {} },
      'Duration': { number: { format: 'number' } },
      'Transcript': { rich_text: {} },
      'Summary': { rich_text: {} },
      'Transcript URL': { url: {} },
      'Audio URL': { url: {} },
      'Transfer To': { rich_text: {} },
      'Call Type': { 
        select: { 
          options: [
            { name: 'Inbound', color: 'blue' },
            { name: 'Outbound', color: 'green' },
            { name: 'Callback', color: 'orange' }
          ] 
        } 
      },
      'Status': { 
        select: { 
          options: [
            { name: 'New', color: 'red' },
            { name: 'Read', color: 'yellow' },
            { name: 'Completed', color: 'green' }
          ] 
        } 
      },
      'Assigned Agent': { 
        select: { 
          options: [
            { name: 'Unassigned', color: 'gray' },
            { name: 'John', color: 'blue' },
            { name: 'Milissa', color: 'purple' },
            { name: 'Colin', color: 'green' },
            { name: 'Samantha (AI)', color: 'orange' }
          ] 
        } 
      },
      'Tasks Created': { relation: { database_id: 'tasks' } }
    }
  },

  // Policies Database
  policies: {
    name: 'Insurance Policies',
    properties: {
      'Policy Number': { title: {} },
      'Customer': { relation: { database_id: 'customers' } },
      'Policy Type': { 
        select: { 
          options: [
            { name: 'Auto', color: 'blue' },
            { name: 'Home', color: 'green' },
            { name: 'Life', color: 'purple' },
            { name: 'Business', color: 'orange' }
          ] 
        } 
      },
      'Premium': { number: { format: 'dollar' } },
      'Start Date': { date: {} },
      'Renewal Date': { date: {} },
      'Status': { 
        select: { 
          options: [
            { name: 'Active', color: 'green' },
            { name: 'Expired', color: 'red' },
            { name: 'Pending', color: 'yellow' }
          ] 
        } 
      },
      'Coverage': { rich_text: {} },
      'Notes': { rich_text: {} }
    }
  },

  // Tasks Database
  tasks: {
    name: 'Tasks & Follow-ups',
    properties: {
      'Task': { title: {} },
      'Customer': { relation: { database_id: 'customers' } },
      'Created From Call': { relation: { database_id: 'calls' } },
      'Assigned To': { 
        select: { 
          options: [
            { name: 'John', color: 'blue' },
            { name: 'Milissa', color: 'purple' },
            { name: 'Colin', color: 'green' },
            { name: 'Samantha (AI)', color: 'orange' }
          ] 
        } 
      },
      'Due Date': { date: {} },
      'Priority': { 
        select: { 
          options: [
            { name: 'High', color: 'red' },
            { name: 'Medium', color: 'yellow' },
            { name: 'Low', color: 'gray' }
          ] 
        } 
      },
      'Status': { 
        select: { 
          options: [
            { name: 'To Do', color: 'red' },
            { name: 'In Progress', color: 'yellow' },
            { name: 'Done', color: 'green' }
          ] 
        } 
      },
      'Notes': { rich_text: {} }
    }
  },

  // Calendar/Appointments Database
  calendar: {
    name: 'Appointments & Callbacks',
    properties: {
      'Title': { title: {} },
      'Customer': { relation: { database_id: 'customers' } },
      'Date & Time': { date: {} },
      'Type': { 
        select: { 
          options: [
            { name: 'Appointment', color: 'blue' },
            { name: 'Callback', color: 'orange' },
            { name: 'Renewal Reminder', color: 'purple' }
          ] 
        } 
      },
      'With': { 
        select: { 
          options: [
            { name: 'John', color: 'blue' },
            { name: 'Milissa', color: 'purple' },
            { name: 'Colin', color: 'green' }
          ] 
        } 
      },
      'Status': { 
        select: { 
          options: [
            { name: 'Scheduled', color: 'yellow' },
            { name: 'Completed', color: 'green' },
            { name: 'Cancelled', color: 'red' }
          ] 
        } 
      },
      'Notes': { rich_text: {} }
    }
  },

  // Communications Database
  communications: {
    name: 'Communications Log',
    properties: {
      'Subject': { title: {} },
      'Customer': { relation: { database_id: 'customers' } },
      'Date': { date: {} },
      'Type': { 
        select: { 
          options: [
            { name: 'Email', color: 'blue' },
            { name: 'SMS', color: 'green' },
            { name: 'Call', color: 'orange' },
            { name: 'Letter', color: 'gray' }
          ] 
        } 
      },
      'Direction': { 
        select: { 
          options: [
            { name: 'Inbound', color: 'blue' },
            { name: 'Outbound', color: 'green' }
          ] 
        } 
      },
      'Content': { rich_text: {} },
      'Attachments': { files: {} }
    }
  }
};

// ============================================================================
// DATABASE INITIALIZATION
// ============================================================================

class NotionDatabaseManager {
  constructor() {
    this.databaseIds = {};
  }

  async initialize() {
    const notion = await getNotionClient();
    
    console.log('🔍 Checking for existing databases...');
    
    // Search for existing databases (Notion API uses 'page' for databases)
    const search = await notion.search({
      filter: { property: 'object', value: 'page' }
    });

    // Map existing databases
    for (const db of search.results) {
      const dbName = db.title[0]?.plain_text;
      for (const [key, schema] of Object.entries(DATABASE_SCHEMAS)) {
        if (dbName === schema.name) {
          this.databaseIds[key] = db.id;
          console.log(`✅ Found existing database: ${schema.name} (${db.id})`);
        }
      }
    }

    // Create missing databases
    for (const [key, schema] of Object.entries(DATABASE_SCHEMAS)) {
      if (!this.databaseIds[key]) {
        await this.createDatabase(key, schema);
      }
    }

    return this.databaseIds;
  }

  async createDatabase(key, schema) {
    const notion = await getNotionClient();
    
    console.log(`📝 Creating database: ${schema.name}...`);

    // Resolve relation database_ids
    const properties = { ...schema.properties };
    for (const [propKey, propValue] of Object.entries(properties)) {
      if (propValue.relation?.database_id) {
        const relatedKey = propValue.relation.database_id;
        if (this.databaseIds[relatedKey]) {
          properties[propKey].relation.database_id = this.databaseIds[relatedKey];
        } else {
          // Remove relation if related DB doesn't exist yet
          delete properties[propKey];
        }
      }
    }

    const database = await notion.databases.create({
      parent: { type: 'page_id', page_id: await this.getOrCreateParentPage() },
      title: [{ type: 'text', text: { content: schema.name } }],
      properties
    });

    this.databaseIds[key] = database.id;
    console.log(`✅ Created database: ${schema.name} (${database.id})`);
    
    return database.id;
  }

  async getOrCreateParentPage() {
    // Priority 1: Use NOTION_PARENT_PAGE_ID from environment
    if (process.env.NOTION_PARENT_PAGE_ID) {
      const pageId = process.env.NOTION_PARENT_PAGE_ID.trim();
      console.log(`🏗  Using parent page from environment: ${pageId}`);
      return pageId;
    }
    
    const notion = await getNotionClient();
    
    // Priority 2: Search for existing CRM page
    const search = await notion.search({
      query: 'Peterson Insurance CRM',
      filter: { property: 'object', value: 'page' }
    });

    if (search.results.length > 0) {
      console.log(`🏗  Found existing parent page: ${search.results[0].id}`);
      return search.results[0].id;
    }

    // If no parent page found and no env variable, throw error
    throw new Error('❌ No parent page found. Please set NOTION_PARENT_PAGE_ID in environment or create a page in Notion and share it with the integration.');
  }
}

// ============================================================================
// AI-MEMORY SYNC
// ============================================================================

class NotionAIMemorySync {
  constructor(databaseIds) {
    this.databaseIds = databaseIds;
  }

  // Sync customer data from Notion to AI-Memory
  async syncCustomerToMemory(customerId) {
    const notion = await getNotionClient();
    
    // Get customer page
    const customer = await notion.pages.retrieve({ page_id: customerId });
    const props = customer.properties;

    const customerData = {
      name: props['Customer Name']?.title[0]?.plain_text,
      phone: props['Phone']?.phone_number,
      email: props['Email']?.email,
      spouse: props['Spouse']?.rich_text[0]?.plain_text,
      children: props['Children']?.rich_text[0]?.plain_text,
      notes: props['Notes']?.rich_text[0]?.plain_text
    };

    const phoneNormalized = customerData.phone?.replace(/\D/g, '');
    
    // Store in AI-Memory
    if (phoneNormalized) {
      const memories = [
        { type: 'person', key: 'caller_name', value: customerData.name },
        { type: 'person', key: 'spouse_name', value: customerData.spouse },
        { type: 'preference', key: 'contact_info', value: JSON.stringify({ email: customerData.email, phone: customerData.phone }) }
      ];

      for (const mem of memories.filter(m => m.value)) {
        await this.writeToAIMemory(mem.type, mem.key, mem.value, phoneNormalized);
      }
    }

    console.log(`✅ Synced customer ${customerData.name} to AI-Memory`);
  }

  // Create/Update customer from phone call
  async upsertCustomerFromCall(phoneNumber, callData) {
    const notion = await getNotionClient();
    
    // Search for existing customer
    const existing = await notion.databases.query({
      database_id: this.databaseIds.customers,
      filter: {
        property: 'Phone',
        phone_number: { equals: phoneNumber }
      }
    });

    const customerProps = {
      'Customer Name': { title: [{ text: { content: callData.name || 'Unknown' } }] },
      'Phone': { phone_number: phoneNumber },
      'Last Call': { date: { start: new Date().toISOString() } },
      'Total Calls': { number: (existing.results[0]?.properties['Total Calls']?.number || 0) + 1 }
    };

    if (callData.email) customerProps['Email'] = { email: callData.email };
    if (callData.spouse) customerProps['Spouse'] = { rich_text: [{ text: { content: callData.spouse } }] };

    let customerId;

    if (existing.results.length > 0) {
      // Update existing
      customerId = existing.results[0].id;
      await notion.pages.update({
        page_id: customerId,
        properties: customerProps
      });
      console.log(`✅ Updated customer ${callData.name}`);
    } else {
      // Create new
      const page = await notion.pages.create({
        parent: { database_id: this.databaseIds.customers },
        properties: customerProps
      });
      customerId = page.id;
      console.log(`✅ Created new customer ${callData.name}`);
    }

    return customerId;
  }

  // Create/Update platform customer (NeuroSphere Voice customer)
  async upsertPlatformCustomer(email, customerData) {
    const notion = await getNotionClient();
    
    // Search for existing platform customer by email
    const existing = await notion.databases.query({
      database_id: this.databaseIds.platform_customers,
      filter: {
        property: 'Email',
        email: { equals: email }
      }
    });

    const platformCustomerProps = {
      'Business Name': { title: [{ text: { content: customerData.business_name || 'Unknown' } }] },
      'Contact Name': { rich_text: [{ text: { content: customerData.contact_name || '' } }] },
      'Email': { email: email },
      'Phone': { phone_number: customerData.phone || '' },
      'Package Tier': { select: { name: customerData.package_tier || 'Starter' } },
      'Status': { select: { name: customerData.status || 'Active' } },
      'Agent Name': { rich_text: [{ text: { content: customerData.agent_name || 'AI Assistant' } }] },
      'Voice Type': { select: { name: customerData.openai_voice || 'alloy' } },
      'Personality Preset': { rich_text: [{ text: { content: customerData.personality_preset || 'professional' } }] },
      'Created Date': { date: { start: new Date().toISOString() } }
    };

    if (customerData.twilio_phone_number) {
      platformCustomerProps['Twilio Number'] = { phone_number: customerData.twilio_phone_number };
    }
    
    if (customerData.greeting_template) {
      platformCustomerProps['Greeting Template'] = { rich_text: [{ text: { content: customerData.greeting_template } }] };
    }

    let customerId;

    if (existing.results.length > 0) {
      // Update existing
      customerId = existing.results[0].id;
      await notion.pages.update({
        page_id: customerId,
        properties: platformCustomerProps
      });
      console.log(`✅ Updated platform customer ${customerData.business_name}`);
    } else {
      // Create new
      const page = await notion.pages.create({
        parent: { database_id: this.databaseIds.platform_customers },
        properties: platformCustomerProps
      });
      customerId = page.id;
      console.log(`✅ Created new platform customer ${customerData.business_name}`);
    }

    return customerId;
  }

  // Log call to Notion
  async logCall(phoneNumber, transcript, summary, transferTo = null, callSid = null, transcriptUrl = null, audioUrl = null) {
    const notion = await getNotionClient();

    // Find customer
    const customer = await notion.databases.query({
      database_id: this.databaseIds.customers,
      filter: { property: 'Phone', phone_number: { equals: phoneNumber } }
    });

    const callProps = {
      'Call Date': { date: { start: new Date().toISOString() } },
      'Phone Number': { phone_number: phoneNumber },
      'Transcript': { rich_text: [{ text: { content: transcript.substring(0, 2000) } }] },
      'Summary': { rich_text: [{ text: { content: summary.substring(0, 2000) } }] },
      'Call Type': { select: { name: 'Inbound' } },
      'Status': { select: { name: 'New' } },  // All new calls start as "New"
      'Assigned Agent': { select: { name: 'Unassigned' } }  // Default to unassigned
    };

    if (callSid) {
      callProps['Call SID'] = { rich_text: [{ text: { content: callSid } }] };
    }

    if (transcriptUrl) {
      callProps['Transcript URL'] = { url: transcriptUrl };
    }

    if (audioUrl) {
      callProps['Audio URL'] = { url: audioUrl };
    }

    if (customer.results.length > 0) {
      callProps['Customer'] = { relation: [{ id: customer.results[0].id }] };
    }

    if (transferTo) {
      callProps['Transfer To'] = { rich_text: [{ text: { content: transferTo } }] };
    }

    await notion.pages.create({
      parent: { database_id: this.databaseIds.calls },
      properties: callProps
    });

    console.log(`✅ Logged call for ${phoneNumber}`);
  }

  // Helper: Write to AI-Memory service
  async writeToAIMemory(type, key, value, userId) {
    try {
      const response = await fetch(`${AI_MEMORY_URL}/memory/write`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          memory_type: type,
          key: key,
          value: value,
          user_id: userId,
          scope: 'user',
          ttl_days: 365
        })
      });

      if (!response.ok) {
        throw new Error(`AI-Memory write failed: ${response.statusText}`);
      }

      console.log(`💾 Wrote to AI-Memory: ${type}:${key} for user ${userId}`);
    } catch (error) {
      console.error(`❌ Failed to write to AI-Memory: ${error.message}`);
    }
  }
}

// ============================================================================
// API ENDPOINTS
// ============================================================================

export async function initializeNotionIntegration() {
  const dbManager = new NotionDatabaseManager();
  const databaseIds = await dbManager.initialize();
  const syncService = new NotionAIMemorySync(databaseIds);
  
  console.log('✅ Notion integration initialized');
  console.log('📊 Database IDs:', databaseIds);
  
  return { databaseIds, syncService };
}

export { NotionDatabaseManager, NotionAIMemorySync };
