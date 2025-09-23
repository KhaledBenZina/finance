#!/bin/bash
# Start (or ensure) postgres is running via docker compose
docker compose -f /home/khaled/spec_proj/finance/ibkr/day_trading/data/docker-compose.yml up -d db
# Wait a bit for DB to be ready
sleep 10
# Activate your Python environment if needed (uncomment and edit if using conda/mamba)
# source /home/khaled/mambaforge/bin/activate perso
# Run the daily fetch script
/home/khaled/mambaforge/envs/perso/bin/python /home/khaled/spec_proj/finance/ibkr/day_trading/data/fetch_ibkr_daily.py
