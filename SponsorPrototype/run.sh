#!/bin/bash
set -e

if command -v conda >/dev/null 2>&1; then 
    source "$(conda info --base)/etc/profile.d/conda.sh"

    if ! conda info --envs | awk '{print $1}' | grep -Fxq "pv-extraction-env"; then
        echo "creating"
        conda env create -f environment.yml
    else
        echo "starting"
    fi

    conda activate pv-extraction-env
else 
    echo "no conda found creating a venv"

    VENV_DIR = ".venv"

    if [! -d "$VENV_DIR"]; then
        echo "creating a venv"
        python -m venv $VENV_DIR
    else 
        echo "using the current"
    fi

    source "$VENV_DIR/bin/activate"

    if [ -f "requrirements.txt"]; then 
        echo "installing"
        pip install -r requirements.txt
    else 
        echo "not found"
    fi 
fi

marimo edit PV-Work/mainScript/notebook.py
