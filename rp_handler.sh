#!/bin/bash
#
# RunPod Serverless Compatibility Wrapper
# This file provides runpod-serverless-start() for GitHub auto-deploy compatibility
# while maintaining the s3fs model mounting functionality

set -e

# RunPod expects this function name for GitHub auto-deploy
default() {
    echo "=========================================="
    echo "ComfyUI Worker - RunPod Serverless Start"
    echo "=========================================="
    
    # Call the actual start script with s3fs mounting
    exec /start.sh "$@"
}

# Alias for RunPod compatibility
runpod-serverless-start() {
    default "$@"
}

# Run the default function
if [ "${1:-}" = "default" ] || [ "${1:-}" = "runpod-serverless-start" ]; then
    shift
fi

default "$@"
