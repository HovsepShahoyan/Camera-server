## Integration with RPOS ONVIF Server

Since your parent directory contains an ONVIF server implementation (RPOS), you can send events from it to this camera_server using the HTTP API.

### Event Trigger Script

Use the included `event_trigger.py` script to send events from RPOS to the camera server:

```bash
# Trigger motion event for camera 'cam1'
python event_trigger.py --camera cam1 --event motion

# Trigger alarm event for camera 'cam2'
python event_trigger.py --camera cam2 --event alarm

# Send repeated motion events every 30 seconds
python event_trigger.py --camera cam1 --event motion --interval 30
```

### Integration Options

#### Option 1: Modify RPOS to Call Event API

In your RPOS `rpos.js` or device service, add HTTP calls to trigger events:

```javascript
// When motion is detected in RPOS
const axios = require('axios');

async function triggerCameraServerEvent(cameraId, eventType) {
  try {
    await axios.post('http://localhost:8555/api/events/motion', {
      camera_id: cameraId,
      event_type: eventType,
      timestamp: Date.now() / 1000,
      metadata: { source: 'rpos' }
    });
    console.log(`Event triggered for camera ${cameraId}`);
  } catch (error) {
    console.error('Failed to trigger camera server event:', error);
  }
}
```

#### Option 2: Use the Event Trigger Script

Call the Python script from your RPOS system:

```bash
# From RPOS (Node.js)
const { exec } = require('child_process');

exec(`python ../camera_server/event_trigger.py --camera cam1 --event motion`, (error, stdout, stderr) => {
  if (error) console.error('Error triggering event:', error);
  else console.log('Event triggered:', stdout);
});
```

### API Endpoints

The camera server exposes these HTTP endpoints for event triggering:

- `POST /api/events/motion` - Trigger motion detection event
- `POST /api/events/alarm` - Trigger alarm event
- `GET /api/status` - Get server status

### Example Event Payload

```json
{
  "camera_id": "cam1",
  "event_type": "motion",
  "timestamp": 1640995200.0,
  "metadata": {
    "source": "rpos_simulator",
    "confidence": 0.95
  }
}
```

### Testing Events

1. Start the camera server: `python camera_server.py`
2. In another terminal, trigger events: `python event_trigger.py --camera cam1 --event motion`
3. Check recordings are created in the `recordings/` directory

This allows your existing RPOS ONVIF server to control event recording in the new camera server without modifying the core RPOS functionality.
