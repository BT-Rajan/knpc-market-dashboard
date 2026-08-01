// pm2 process definition for the KNPC backend. Run from the repo root:
//   pm2 start ecosystem.config.js
//   pm2 save
// Uses the venv created by scripts/install.sh -- run that first.
module.exports = {
  apps: [
    {
      name: "knpc-dashboard",
      cwd: "./backend",
      script: "venv/bin/python",
      args: "run.py",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      out_file: "logs/pm2-out.log",
      error_file: "logs/pm2-error.log",
      time: true,
    },
  ],
};
