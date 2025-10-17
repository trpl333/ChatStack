/**
 * Notion API Server for Peterson Insurance
 * 
 * Provides HTTP endpoints for the phone system to interact with Notion
 * Runs as a standalone service alongside Flask/FastAPI
 */

import express from 'express';
import { initializeNotionIntegration } from './notion-sync.js';

const app = express();
app.use(express.json());

let syncService = null;
let databaseIds = null;

// Initialize Notion on startup
(async () => {
  try {
    const result = await initializeNotionIntegration();
    syncService = result.syncService;
    databaseIds = result.databaseIds;
    console.log('✅ Notion sync service ready');
  } catch (error) {
    console.error('❌ Failed to initialize Notion:', error);
  }
})();

// ============================================================================
// ENDPOINTS FOR PHONE SYSTEM
// ============================================================================

/**
 * POST /notion/customer
 * Upsert customer from call data
 * 
 * Body: {
 *   phone: "+19495565377",
 *   name: "John Smith", 
 *   email: "john@example.com",
 *   spouse: "Kelly"
 * }
 */
app.post('/notion/customer', async (req, res) => {
  try {
    const { phone, name, email, spouse } = req.body;
    
    const customerId = await syncService.upsertCustomerFromCall(phone, {
      name,
      email,
      spouse
    });

    res.json({ 
      success: true, 
      customer_id: customerId,
      message: 'Customer synced to Notion'
    });
  } catch (error) {
    console.error('Error upserting customer:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * POST /notion/platform-customer
 * Create or update a NeuroSphere Voice platform customer
 * 
 * Body: {
 *   email: "john@agency.com",
 *   business_name: "ABC Insurance Agency",
 *   contact_name: "John Smith",
 *   phone: "555-1234",
 *   package_tier: "Professional",
 *   agent_name: "Sarah",
 *   openai_voice: "nova",
 *   personality_preset: "friendly",
 *   greeting_template: "Hi, this is {agent_name}...",
 *   twilio_phone_number: "+15551234567" (optional),
 *   status: "Active"
 * }
 */
app.post('/notion/platform-customer', async (req, res) => {
  try {
    const { email, ...customerData } = req.body;
    
    const customerId = await syncService.upsertPlatformCustomer(email, customerData);

    res.json({ 
      success: true, 
      customer_id: customerId,
      message: 'Platform customer synced to Notion'
    });
  } catch (error) {
    console.error('Error upserting platform customer:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * POST /notion/call-log
 * Log a call to Notion
 * 
 * Body: {
 *   phone: "+19495565377",
 *   transcript: "Full conversation...",
 *   summary: "Customer called about...",
 *   transfer_to: "John" (optional),
 *   call_sid: "CAxxxxxxx" (optional),
 *   transcript_url: "https://voice.theinsurancedoctors.com/calls/CAxxxx.txt" (optional),
 *   audio_url: "https://voice.theinsurancedoctors.com/calls/CAxxxx.mp3" (optional)
 * }
 */
app.post('/notion/call-log', async (req, res) => {
  try {
    const { phone, transcript, summary, transfer_to, call_sid, transcript_url, audio_url } = req.body;
    
    await syncService.logCall(phone, transcript, summary, transfer_to, call_sid, transcript_url, audio_url);

    res.json({ 
      success: true,
      message: 'Call logged to Notion'
    });
  } catch (error) {
    console.error('Error logging call:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * POST /notion/sync-to-memory
 * Sync a customer's Notion data to AI-Memory
 * 
 * Body: {
 *   customer_id: "notion-page-id"
 * }
 */
app.post('/notion/sync-to-memory', async (req, res) => {
  try {
    const { customer_id } = req.body;
    
    await syncService.syncCustomerToMemory(customer_id);

    res.json({ 
      success: true,
      message: 'Customer data synced to AI-Memory'
    });
  } catch (error) {
    console.error('Error syncing to memory:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * GET /notion/databases
 * Get all database IDs
 */
app.get('/notion/databases', (req, res) => {
  res.json({ 
    success: true,
    databases: databaseIds
  });
});

/**
 * GET /health
 * Health check
 */
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok',
    notion_ready: syncService !== null,
    databases: Object.keys(databaseIds || {}).length
  });
});

// ============================================================================
// START SERVER
// ============================================================================

const PORT = process.env.NOTION_API_PORT || 8200;

app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Notion API Server running on http://0.0.0.0:${PORT}`);
  console.log(`📊 Databases initialized: ${Object.keys(databaseIds || {}).length}`);
});
