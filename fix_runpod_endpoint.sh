#!/bin/bash
# DEPRECATED: This script is for legacy RunPod endpoint configuration
# All environments now use OpenAI API via config.json as the source of truth
# Use fix_llm_config.sh to ensure proper OpenAI configuration

echo "⚠️  DEPRECATED: RunPod endpoint configuration no longer supported"
echo "📄 All environments now use OpenAI API (https://api.openai.com/v1)"
echo "🔧 Run 'bash fix_llm_config.sh' to ensure proper OpenAI configuration"
echo ""
echo "This script is kept for reference only and should not be used."
echo "Exiting..."
exit 1