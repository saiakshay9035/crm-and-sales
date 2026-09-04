module.exports = {
  apps: [
    {
      name: "lead-capture-agent",
      script: "dashboard.py",
      interpreter: "python",
      cwd: "C:\\Users\\SAIAKSHAY R\\.gemini\\antigravity\\scratch\\ai_lead_crm_agent",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
