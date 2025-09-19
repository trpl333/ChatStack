# OpenAI Realtime API Integration

This document explains how ChatStack supports OpenAI's Realtime API for real-time conversational AI using WebSocket connections.

## Overview

ChatStack now supports both REST API and Realtime API modes:

- **REST API Mode**: Traditional HTTP requests to `/v1/chat/completions` (default for models like `gpt-4o`, `gpt-3.5-turbo`)
- **Realtime API Mode**: WebSocket connection to `/v1/realtime` (for models like `gpt-realtime-2025-08-28`)

The system automatically detects which mode to use based on the model name in your configuration.

## Configuration

### Setting up Realtime API

1. **Update config.json**:
   ```json
   {
     "llm_model": "gpt-realtime-2025-08-28",
     "llm_base_url": "https://api.openai.com/v1"
   }
   ```

2. **Set your OpenAI API Key**:
   ```bash
   export OPENAI_API_KEY="your-openai-api-key-here"
   ```

3. **Install WebSocket dependencies**:
   ```bash
   pip install websocket-client
   ```

### Model Detection

The system automatically detects Realtime models by checking if "realtime" is in the model name (case-insensitive):

- ✅ `gpt-realtime-2025-08-28` → Uses Realtime API
- ✅ `gpt-realtime-beta` → Uses Realtime API  
- ❌ `gpt-4o` → Uses REST API
- ❌ `gpt-3.5-turbo` → Uses REST API

## How It Works

### Realtime API Flow

1. **Connection**: Opens WebSocket to `wss://api.openai.com/v1/realtime?model=gpt-realtime-2025-08-28`
2. **Authentication**: Uses `Authorization: Bearer {api_key}` header
3. **Session Setup**: Sends `session.update` with configuration
4. **Conversation**: Sends conversation history as `conversation.item.create` events
5. **Response**: Receives real-time streaming response deltas
6. **Streaming**: Yields tokens as they arrive for immediate display

### Event Handling

The implementation handles these Realtime API events:

- `session.created` - Confirms session is ready
- `session.updated` - Confirms configuration applied
- `conversation.item.created` - Confirms message added
- `response.created` - Response generation started
- `response.text.delta` - Streaming text chunks
- `response.done` - Response complete
- `error` - API errors

### Fallback Mechanism

If WebSocket client is unavailable, the system automatically falls back to REST API mode:

```python
if WebSocketApp is None:
    # Falls back to regular chat() function
    response_content, _ = chat(messages, temperature=temperature, max_tokens=max_tokens)
    # Simulates streaming by splitting into words
    for word in response_content.split():
        yield word + " "
```

## Code Structure

### Key Files

- `app/llm.py` - Contains `chat_realtime_stream()` function
- `app/main.py` - Routing logic to detect realtime models
- `config.json` - Model configuration
- `test_realtime_api.py` - Integration test script

### Function Flow

```python
# In app/main.py
config = _get_llm_config()
if "realtime" in config["model"].lower():
    # Use Realtime API
    for token in chat_realtime_stream(final_messages, temperature, max_tokens):
        tokens.append(token)
else:
    # Use REST API
    response_content, usage = llm_chat(final_messages, temperature, max_tokens)
```

## Testing

Run the integration test to verify your setup:

```bash
python test_realtime_api.py
```

This will check:
- ✅ Configuration is loaded correctly
- ✅ Model type is detected properly  
- ✅ WebSocket client is available
- ✅ Backend routing logic works
- ✅ Fallback mechanism functions

## Admin Interface

The admin interface at `/admin` shows:

- **Current Model**: Displays the active model name
- **API Type**: Shows "REST" or "Realtime WebSocket" 
- **Status**: Green for Realtime, gray for REST

## Troubleshooting

### Common Issues

1. **WebSocket not available**
   ```
   Solution: pip install websocket-client
   ```

2. **API key not set**
   ```
   Solution: export OPENAI_API_KEY="your-key"
   ```

3. **Connection timeout**
   ```
   Check: Internet connectivity and API key validity
   ```

4. **Fallback to REST**
   ```
   Expected behavior when WebSocket unavailable
   ```

### Debug Logging

Enable debug logging to see WebSocket events:

```python
import logging
logging.getLogger('websocket').setLevel(logging.DEBUG)
```

## API Differences

| Feature | REST API | Realtime API |
|---------|----------|--------------|
| Connection | HTTP Request | WebSocket |
| Response | Complete | Streaming |
| Latency | Higher | Lower |
| Setup | Simple | Requires WebSocket |
| Fallback | N/A | Falls back to REST |

## Dependencies

### Required
- `websocket-client` - WebSocket client library
- `openai` - OpenAI SDK (optional, used for validation)

### Optional  
- `fastapi` - Web framework
- `uvicorn` - ASGI server

## Security Considerations

- API keys are passed in WebSocket headers
- Connection uses WSS (secure WebSocket)
- No API keys stored in config files
- Environment variables used for secrets

## Performance

### Realtime API Benefits
- Lower latency for streaming responses
- Real-time conversational experience
- Better user experience for chat applications

### REST API Benefits  
- Simpler implementation
- More reliable for batch processing
- Better for non-interactive use cases

## Support

For issues with:
- **OpenAI Realtime API**: Check OpenAI documentation
- **WebSocket connections**: Verify network/firewall settings
- **ChatStack integration**: Run `test_realtime_api.py` for diagnostics