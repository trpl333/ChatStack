#!/bin/bash
# Test LLM endpoint connectivity using config.json values
echo "🧪 Testing LLM endpoint connectivity (sourced from config.json)..."

# Read LLM configuration from config.json
if [ -f "config.json" ]; then
    LLM_BASE_URL=$(grep -o '"llm_base_url": "[^"]*"' config.json | cut -d'"' -f4)
    LLM_MODEL=$(grep -o '"llm_model": "[^"]*"' config.json | cut -d'"' -f4)
    echo "📄 Using config from config.json:"
    echo "   Base URL: $LLM_BASE_URL"
    echo "   Model: $LLM_MODEL"
else
    echo "❌ config.json not found, using defaults"
    LLM_BASE_URL="https://api.openai.com/v1"
    LLM_MODEL="gpt-realtime-2025-08-28"
fi

# Test basic connectivity
echo ""
echo "1. Testing basic HTTP connectivity..."
curl -I "$LLM_BASE_URL" --timeout 10

echo ""
echo "2. Testing LLM endpoint with sample request..."
# Note: This will fail without OPENAI_API_KEY, but tests connectivity
curl -X POST "$LLM_BASE_URL/chat/completions" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer \$OPENAI_API_KEY" \
     -d "{
       \"model\": \"$LLM_MODEL\",
       \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}],
       \"max_tokens\": 100,
       \"temperature\": 0.7
     }" \
     --timeout 15 \
     --verbose

echo ""
echo "3. Testing models endpoint..."
curl -I "$LLM_BASE_URL/models" --timeout 10

echo ""
echo "✅ Test complete!"
echo "💡 Note: Actual API calls require valid OPENAI_API_KEY environment variable"