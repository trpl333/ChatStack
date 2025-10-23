module.exports = {
  apps: [{
    name: 'leadflow-tracker',
    script: 'npm',
    args: 'start',
    cwd: '/opt/LeadFlowTracker',
    env: {
      NODE_ENV: 'production',
      PORT: 5001
    },
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    error_file: '/var/log/leadflow/error.log',
    out_file: '/var/log/leadflow/out.log',
    log_file: '/var/log/leadflow/combined.log',
    time: true
  }]
};
