# Setup Guide for Other Replits

This guide shows how to set up AI-Memory, LeadFlowTracker, and neurosphere_send_text Replits to stay synchronized with ChatStack architecture.

---

## 📋 Setup Steps (Do This Once Per Replit)

### Step 1: Copy Files to Each Replit

**Files needed in EACH Replit:**
1. `MULTI_PROJECT_ARCHITECTURE.md` - The shared architecture doc
2. `sync_architecture.sh` - The sync script

**How to add them:**

#### Option A: Create Files Manually
1. Open the Replit (e.g., AI-Memory)
2. Click "+ Add file" → Create `MULTI_PROJECT_ARCHITECTURE.md`
3. Copy content from: https://github.com/trpl333/ChatStack/blob/main/MULTI_PROJECT_ARCHITECTURE.md
4. Click "+ Add file" → Create `sync_architecture.sh`
5. Copy content from: https://github.com/trpl333/ChatStack/blob/main/sync_architecture.sh
6. In Shell: `chmod +x sync_architecture.sh`

#### Option B: Download from GitHub (Faster)
```bash
# In each Replit's Shell:
curl -o MULTI_PROJECT_ARCHITECTURE.md https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md
curl -o sync_architecture.sh https://raw.githubusercontent.com/trpl333/ChatStack/main/sync_architecture.sh
chmod +x sync_architecture.sh
```

---

## 🔄 Daily Usage Workflow

### Before Starting Work in ANY Replit:
```bash
# Pull latest architecture to see changes from other services
./sync_architecture.sh pull
```

### After Making Changes to Your Service:
```bash
# 1. Update MULTI_PROJECT_ARCHITECTURE.md with your changes
# 2. Push to GitHub so other Replits can sync
./sync_architecture.sh push
```

---

## 📝 Agent Instructions for Each Replit

**Add this to each Replit's `replit.md` file:**

```markdown
## Architecture Sync (CRITICAL)

**Before working on this project:**
```bash
./sync_architecture.sh pull
```

**After making changes that affect architecture:**
1. Update the relevant section in `MULTI_PROJECT_ARCHITECTURE.md`
2. Run: `./sync_architecture.sh push`
3. This notifies other services of your changes

**GitHub Master:**
https://github.com/trpl333/ChatStack/blob/main/MULTI_PROJECT_ARCHITECTURE.md
```

---

## 🎯 How It Works

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌─────────────┐
│  ChatStack  │      │  AI-Memory   │      │LeadFlowTrkr │      │  SendText   │
│   Replit    │      │   Replit     │      │   Replit    │      │   Replit    │
└──────┬──────┘      └──────┬───────┘      └──────┬──────┘      └──────┬──────┘
       │                    │                     │                    │
       │  pull              │  pull               │  pull              │  pull
       ▼                    ▼                     ▼                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                    GitHub (Single Source of Truth)                         │
│          https://github.com/trpl333/ChatStack/                            │
│          MULTI_PROJECT_ARCHITECTURE.md                                     │
└────────────────────────────────────────────────────────────────────────────┘
       ▲                    ▲                     ▲                    ▲
       │  push              │  push               │  push              │  push
       └────────────────────┴─────────────────────┴────────────────────┘
```

**Key Points:**
- ✅ GitHub is the master - not any single Replit
- ✅ All Replits pull from GitHub (always get latest)
- ✅ Any Replit can push updates to GitHub (share changes)
- ✅ ChatGPT reads directly from GitHub (always current)

---

## 🚨 Example Scenarios

### Scenario 1: AI-Memory Adds New Endpoint
```bash
# In AI-Memory Replit:
./sync_architecture.sh pull          # Get latest first

# Make code changes, add /v2/caller/profile endpoint
# Then update MULTI_PROJECT_ARCHITECTURE.md:
#   - Add endpoint to AI-Memory section
#   - Document parameters and response

./sync_architecture.sh push          # Share with everyone
# (Script asks for new version: 1.2.0 → 1.3.0)

# Now ChatStack, LeadFlow, SendText can pull and see the new endpoint!
```

### Scenario 2: ChatStack Needs to Call AI-Memory
```bash
# In ChatStack Replit:
./sync_architecture.sh pull          # Get latest architecture

# Check MULTI_PROJECT_ARCHITECTURE.md for AI-Memory endpoints
# Use exact endpoints from documentation
# No more guessing - use real endpoint specs!
```

### Scenario 3: ChatGPT Consultation
```
User pastes into ChatGPT:
"Please review my architecture from:
https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md

I want to add lead tracking to phone calls. How should ChatStack 
integrate with LeadFlowTracker?"

ChatGPT reads the doc and sees:
- ChatStack endpoints
- LeadFlowTracker endpoints (/api/leads)
- AI-Memory endpoints for caller data
- Can give accurate integration advice!
```

---

## ✅ Verification

**To verify setup is working:**

```bash
# Check you have the script
ls -l sync_architecture.sh

# Check current version
./sync_architecture.sh version

# Pull latest (should work without errors)
./sync_architecture.sh pull
```

---

## 📚 Reference

**GitHub Master File:**
https://github.com/trpl333/ChatStack/blob/main/MULTI_PROJECT_ARCHITECTURE.md

**Raw URL (for ChatGPT):**
https://raw.githubusercontent.com/trpl333/ChatStack/main/MULTI_PROJECT_ARCHITECTURE.md

**All 4 Repos:**
- ChatStack: https://github.com/trpl333/ChatStack
- AI-Memory: https://github.com/trpl333/ai-memory
- LeadFlowTracker: https://github.com/trpl333/LeadFlowTracker
- SendText: https://github.com/trpl333/neurosphere_send_text
