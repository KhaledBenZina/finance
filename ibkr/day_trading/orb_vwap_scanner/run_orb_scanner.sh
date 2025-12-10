#!/bin/bash
# Quick script to run the ORB + VWAP Scanner UI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate perso conda environment
source /home/khaled/mambaforge/bin/activate perso

# Use python -m streamlit to ensure we use the conda environment's Python
python -m streamlit run orb_vwap_ui.py --server.port 8501

