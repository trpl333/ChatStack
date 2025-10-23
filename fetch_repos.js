import { Octokit } from '@octokit/rest';
import fs from 'fs';
import path from 'path';

let connectionSettings;

async function getAccessToken() {
  if (connectionSettings && connectionSettings.settings.expires_at && new Date(connectionSettings.settings.expires_at).getTime() > Date.now()) {
    return connectionSettings.settings.access_token;
  }
  
  const hostname = process.env.REPLIT_CONNECTORS_HOSTNAME;
  const xReplitToken = process.env.REPL_IDENTITY 
    ? 'repl ' + process.env.REPL_IDENTITY 
    : process.env.WEB_REPL_RENEWAL 
    ? 'depl ' + process.env.WEB_REPL_RENEWAL 
    : null;

  if (!xReplitToken) {
    throw new Error('X_REPLIT_TOKEN not found for repl/depl');
  }

  connectionSettings = await fetch(
    'https://' + hostname + '/api/v2/connection?include_secrets=true&connector_names=github',
    {
      headers: {
        'Accept': 'application/json',
        'X_REPLIT_TOKEN': xReplitToken
      }
    }
  ).then(res => res.json()).then(data => data.items?.[0]);

  const accessToken = connectionSettings?.settings?.access_token || connectionSettings.settings?.oauth?.credentials?.access_token;

  if (!connectionSettings || !accessToken) {
    throw new Error('GitHub not connected');
  }
  return accessToken;
}

async function getUncachableGitHubClient() {
  const accessToken = await getAccessToken();
  return new Octokit({ auth: accessToken });
}

async function downloadRepo(owner, repo, targetDir) {
  console.log(`\n📥 Fetching ${repo}...`);
  const octokit = await getUncachableGitHubClient();
  
  try {
    // Get default branch
    const repoInfo = await octokit.repos.get({ owner, repo });
    const defaultBranch = repoInfo.data.default_branch;
    console.log(`   ✓ Found repo, default branch: ${defaultBranch}`);
    
    // Get tree recursively
    const tree = await octokit.git.getTree({
      owner,
      repo,
      tree_sha: defaultBranch,
      recursive: true
    });
    
    console.log(`   ✓ Found ${tree.data.tree.length} items in repo`);
    
    // Create target directory
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
    }
    
    // Download files (skip directories and large files)
    let downloaded = 0;
    for (const item of tree.data.tree) {
      if (item.type === 'blob' && item.size < 1000000) { // Skip files > 1MB
        try {
          const fileContent = await octokit.git.getBlob({
            owner,
            repo,
            file_sha: item.sha
          });
          
          const filePath = path.join(targetDir, item.path);
          const dirPath = path.dirname(filePath);
          
          // Create directory if needed
          if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
          }
          
          // Write file
          const content = Buffer.from(fileContent.data.content, 'base64');
          fs.writeFileSync(filePath, content);
          downloaded++;
        } catch (err) {
          console.log(`   ⚠ Skipped ${item.path}: ${err.message}`);
        }
      }
    }
    
    console.log(`   ✓ Downloaded ${downloaded} files to ${targetDir}`);
    return true;
  } catch (error) {
    console.error(`   ✗ Error downloading ${repo}: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('🚀 Starting GitHub repo download...\n');
  
  const repos = [
    { owner: 'trpl333', repo: 'ai-memory', dir: 'external/ai-memory' },
    { owner: 'trpl333', repo: 'LeadFlowTracker', dir: 'external/LeadFlowTracker' },
    { owner: 'trpl333', repo: 'neurosphere_send_text', dir: 'external/neurosphere_send_text' }
  ];
  
  for (const { owner, repo, dir } of repos) {
    await downloadRepo(owner, repo, dir);
  }
  
  console.log('\n✅ All repos downloaded!\n');
  console.log('📂 Files saved to:');
  repos.forEach(r => console.log(`   - ${r.dir}`));
}

main().catch(err => {
  console.error('❌ Fatal error:', err);
  process.exit(1);
});
