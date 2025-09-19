#!/bin/bash
# Script to ensure LLM configuration uses OpenAI from config.json
# Run this on your server: bash fix_llm_config.sh

echo "🔧 Ensuring LLM configuration uses OpenAI from config.json..."

cd /opt/ChatStack 2>/dev/null || cd .

# Clear any old environment variables that override config.json
echo "🧹 Clearing old LLM environment variables..."
unset LLM_BASE_URL
unset LLM_MODEL

# Update config.json if it exists to ensure OpenAI values
echo "⚙️ Updating config.json with OpenAI configuration..."
if [ -f config.json ]; then
    # Create backup
    cp config.json config.json.backup.$(date +%Y%m%d_%H%M%S)
    
    # Update or add llm_base_url in config.json
    if grep -q "llm_base_url" config.json; then
        sed -i 's|"llm_base_url": ".*"|"llm_base_url": "https://api.openai.com/v1"|' config.json
    else
        # Add llm_base_url to config.json
        sed -i '2i\  "llm_base_url": "https://api.openai.com/v1",' config.json
    fi
    
    if grep -q "llm_model" config.json; then
        sed -i 's|"llm_model": ".*"|"llm_model": "gpt-realtime-2025-08-28"|' config.json
    else
        sed -i '3i\  "llm_model": "gpt-realtime-2025-08-28",' config.json
    fi
    
    echo "✅ Updated config.json with OpenAI configuration"
else
    echo "❌ config.json not found - creating with OpenAI defaults"
    cat > config.json << EOF
{
  "comment": "NeuroSphere Orchestrator Configuration - Non-sensitive settings only",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_model": "gpt-realtime-2025-08-28",
  "embed_dim": 768,
  "port": 5000,
  "environment": "production"
}
EOF
fi

echo "🧪 Testing OpenAI endpoint connectivity..."
# Note: This will fail without API key but tests basic connectivity
curl -I "https://api.openai.com/v1" --timeout 10

if [ $? -eq 0 ]; then
    echo "✅ OpenAI endpoint is reachable!"
else
    echo "❌ OpenAI endpoint test failed - check network connectivity"
fi

echo "🚀 Redeploying application..."
if [ -f docker-compose.yml ]; then
    docker-compose down
    docker-compose up -d --build
else
    echo "⚠️  docker-compose.yml not found - restart services manually"
fi

echo "⏳ Waiting for application to start..."
sleep 15

echo "📞 Testing phone system..."
if command -v curl >/dev/null 2>&1; then
    TEST_RESULT=$(curl -s -X POST https://voice.theinsurancedoctors.com/phone/incoming \
         -d "From=+test&To=+19497071290" 2>/dev/null)

    if echo "$TEST_RESULT" | grep -q "Play\|Say"; then
        echo "✅ Phone system is responding!"
    else
        echo "❌ Phone system test failed or requires setup"
    fi
fi

echo ""
echo "🎉 LLM configuration standardized to OpenAI!"
echo ""
echo "📋 Configuration Summary:"
echo "  • LLM Backend: https://api.openai.com/v1"  
echo "  • Model: gpt-realtime-2025-08-28"
echo "  • Source: config.json (single source of truth)"
echo ""
echo "💡 To verify:"
echo "1. Check config.json for llm_base_url and llm_model values"
echo "2. Ensure OPENAI_API_KEY environment variable is set"
echo "3. Try calling: +19497071290"
echo "4. Check logs: docker-compose logs -f web | grep -E 'LLM|OpenAI'"