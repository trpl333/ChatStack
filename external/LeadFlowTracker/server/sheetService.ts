import { getUncachableGoogleSheetClient } from './googleSheets';
import type { Lead } from '@shared/schema';

const SPREADSHEET_TITLE = 'Sales Lead Tracker';
const SHEET_NAME = 'Leads';

const HEADERS = [
  'ID',
  'Name',
  'Company',
  'Phone',
  'Email',
  'Source',
  'Current Stage',
  'Completed Milestones',
  'Notes',
  'Created At',
  'Updated At',
  'Stage Entered At'
];

let cachedSpreadsheetId: string | null = null;

async function getOrCreateSpreadsheet() {
  if (cachedSpreadsheetId) {
    try {
      const sheets = await getUncachableGoogleSheetClient();
      await sheets.spreadsheets.get({ spreadsheetId: cachedSpreadsheetId });
      return cachedSpreadsheetId;
    } catch (error) {
      cachedSpreadsheetId = null;
    }
  }

  const sheets = await getUncachableGoogleSheetClient();
  
  try {
    const response = await sheets.spreadsheets.create({
      requestBody: {
        properties: {
          title: SPREADSHEET_TITLE,
        },
        sheets: [
          {
            properties: {
              title: SHEET_NAME,
            },
          },
        ],
      },
    });

    const spreadsheetId = response.data.spreadsheetId!;
    cachedSpreadsheetId = spreadsheetId;

    await sheets.spreadsheets.values.update({
      spreadsheetId,
      range: `${SHEET_NAME}!A1:L1`,
      valueInputOption: 'RAW',
      requestBody: {
        values: [HEADERS],
      },
    });

    await sheets.spreadsheets.batchUpdate({
      spreadsheetId,
      requestBody: {
        requests: [
          {
            repeatCell: {
              range: {
                sheetId: 0,
                startRowIndex: 0,
                endRowIndex: 1,
              },
              cell: {
                userEnteredFormat: {
                  textFormat: {
                    bold: true,
                  },
                  backgroundColor: {
                    red: 0.9,
                    green: 0.9,
                    blue: 0.9,
                  },
                },
              },
              fields: 'userEnteredFormat(textFormat,backgroundColor)',
            },
          },
        ],
      },
    });

    console.log(`Created new spreadsheet: ${spreadsheetId}`);
    return spreadsheetId;
  } catch (error) {
    console.error('Error creating spreadsheet:', error);
    throw error;
  }
}

function leadToRow(lead: Lead): any[] {
  return [
    lead.id,
    lead.name,
    lead.company,
    lead.phone,
    lead.email,
    lead.source,
    lead.currentStage,
    (lead.completedMilestones || []).join(', '),
    lead.notes || '',
    new Date(lead.createdAt).toISOString(),
    new Date(lead.updatedAt).toISOString(),
    new Date(lead.stageEnteredAt).toISOString(),
  ];
}

export async function syncLeadToSheet(lead: Lead) {
  try {
    const spreadsheetId = await getOrCreateSpreadsheet();
    const sheets = await getUncachableGoogleSheetClient();

    const existingData = await sheets.spreadsheets.values.get({
      spreadsheetId,
      range: `${SHEET_NAME}!A:A`,
    });

    const rows = existingData.data.values || [];
    const leadRowIndex = rows.findIndex((row, index) => index > 0 && row[0] === lead.id);

    const rowData = leadToRow(lead);

    if (leadRowIndex >= 0) {
      await sheets.spreadsheets.values.update({
        spreadsheetId,
        range: `${SHEET_NAME}!A${leadRowIndex + 1}:L${leadRowIndex + 1}`,
        valueInputOption: 'RAW',
        requestBody: {
          values: [rowData],
        },
      });
    } else {
      await sheets.spreadsheets.values.append({
        spreadsheetId,
        range: `${SHEET_NAME}!A:L`,
        valueInputOption: 'RAW',
        requestBody: {
          values: [rowData],
        },
      });
    }

    return true;
  } catch (error) {
    console.error('Error syncing lead to sheet:', error);
    throw error;
  }
}

export async function syncAllLeadsToSheet(leads: Lead[]) {
  try {
    const spreadsheetId = await getOrCreateSpreadsheet();
    const sheets = await getUncachableGoogleSheetClient();

    const values = [HEADERS, ...leads.map(leadToRow)];

    await sheets.spreadsheets.values.clear({
      spreadsheetId,
      range: `${SHEET_NAME}!A:L`,
    });

    await sheets.spreadsheets.values.update({
      spreadsheetId,
      range: `${SHEET_NAME}!A1:L${values.length}`,
      valueInputOption: 'RAW',
      requestBody: {
        values,
      },
    });

    await sheets.spreadsheets.batchUpdate({
      spreadsheetId,
      requestBody: {
        requests: [
          {
            repeatCell: {
              range: {
                sheetId: 0,
                startRowIndex: 0,
                endRowIndex: 1,
              },
              cell: {
                userEnteredFormat: {
                  textFormat: {
                    bold: true,
                  },
                  backgroundColor: {
                    red: 0.9,
                    green: 0.9,
                    blue: 0.9,
                  },
                },
              },
              fields: 'userEnteredFormat(textFormat,backgroundColor)',
            },
          },
        ],
      },
    });

    return true;
  } catch (error) {
    console.error('Error syncing all leads to sheet:', error);
    throw error;
  }
}
