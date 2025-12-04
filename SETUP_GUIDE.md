# Camera Server Setup Guide

## Overview
This camera server integrates with Shinobi and ONVIF cameras for event-based recording. It processes RTSP streams, monitors ONVIF events, and provides an HTTP API for manual event triggering.

## Prerequisites

### System Requirements
- Python 3.12 or higher
- Ubuntu/Debian Linux (tested on Ubuntu)
- Network access to cameras and Shinobi server

### Required System Packages
```bash
sudo apt update
sudo apt install -y \
  build-essential \
  python3.12-dev \
  python3-pip \
  libffi-dev \
  libglib2.0-dev \
  pkg-config \
  ffmpeg
```

## Installation Steps

### 1. Create Virtual Environment
```bash
cd ~/Camera-server
python3 -m venv venv312
source venv312/bin/activate
```

### 2. Install Python Dependencies
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

**Note:** The `gstreamer-python` dependency is commented out in `requirements.txt` because it's optional and can cause installation issues. The server uses OpenCV for video processing instead.

### 3. Configure the Server

Edit `config.json` with your actual settings:

#### Shinobi Configuration
Replace placeholder values:
```json
"shinobi": {
  "base_url": "http://localhost:8080",
  "api_key": "YOUR_ACTUAL_API_KEY",
  "group_key": "YOUR_ACTUAL_GROUP_KEY"
}
```

To get Shinobi API keys:
1. Log into Shinobi web interface
2. Go to Settings → API
3. Copy your API Key and Group Key

#### Camera Configuration
Update camera details:
```json
"cameras": [
  {
    "id": "cam1",
    "name": "Front Door Camera",
    "rtsp_url": "rtsp://admin:password@192.168.1.100:554/stream1",
    "onvif_url": "http://192.168.1.100:80/onvif/device_service",
    "username": "admin",
    "password": "your_camera_password"
  }
]
```

**RTSP URL Format:**
- `rtsp://username:password@camera_ip:port/stream_path`
- Common ports: 554 (RTSP), 8554 (alternative)
- Common paths: `/stream1`, `/Streaming/Channels/101`, `/live`

**ONVIF URL Format:**
- `http://camera_ip:port/onvif/device_service`
- Common ports: 80, 8080
- Path is usually `/onvif/device_service`

### 4. Verify Setup
```bash
python3 test_setup.py
```

This checks:
- All dependencies are installed
- Configuration is valid
- Recording directory is writable

## Running the Server

### Start the Server
```bash
source venv312/bin/activate
python3 camera_server.py
```

The server will:
1. Start HTTP API on port 8555
2. Initialize cameras in Shinobi
3. Begin RTSP stream processing
4. Start ONVIF event monitoring

### Check Server Status
```bash
curl http://localhost:8555/api/status
```

Expected response:
```json
{
  "running": true,
  "cameras": 1,
  "camera_ids": ["cam1"]
}
```

## Testing

### Manual Event Triggering
```bash
# Trigger motion event
python3 event_trigger.py --camera cam1 --event motion

# Trigger alarm event
python3 event_trigger.py --camera cam1 --event alarm

# Continuous triggering every 30 seconds
python3 event_trigger.py --camera cam1 --event motion --interval 30
```

### Using curl
```bash
# Trigger motion event
curl -X POST http://localhost:8555/api/events/motion \
  -H "Content-Type: application/json" \
  -d '{"camera_id": "cam1", "event_type": "motion", "timestamp": 1640995200.0}'

# Trigger alarm event
curl -X POST http://localhost:8555/api/events/alarm \
  -H "Content-Type: application/json" \
  -d '{"camera_id": "cam1", "event_type": "alarm", "timestamp": 1640995200.0}'
```

## Troubleshooting

### Connection Refused Error
**Error:** `Connection refused on localhost:8555`

**Solution:**
1. Ensure the camera server is running: `python3 camera_server.py`
2. Check if port 8555 is available: `netstat -tuln | grep 8555`
3. Verify config.json has correct port (8555)

### PyGObject Installation Fails
**Error:** `girepository-2.0 not found`

**Solution:** This is expected! The `gstreamer-python` dependency is optional and commented out in `requirements.txt`. The server uses OpenCV instead, which is already installed.

### RTSP Stream Connection Failed
**Error:** `Failed to open RTSP stream`

**Solutions:**
1. Verify camera IP and credentials
2. Test RTSP URL with VLC or ffplay:
   ```bash
   ffplay rtsp://username:password@camera_ip:554/stream
   ```
3. Check network connectivity: `ping camera_ip`
4. Ensure camera supports RTSP

### ONVIF Connection Failed
**Error:** `Failed to connect to ONVIF camera`

**Solutions:**
1. Verify ONVIF is enabled on camera
2. Check ONVIF URL and port (usually 80 or 8080)
3. Test with ONVIF Device Manager tool
4. Ensure camera supports ONVIF Profile S

### Shinobi Connection Failed
**Error:** `Shinobi API request failed`

**Solutions:**
1. Verify Shinobi is running: `curl http://localhost:8080`
2. Check API key and group key in config.json
3. Ensure Shinobi is accessible from camera server

## File Structure

```
Camera-server/
├── camera_server.py       # Main server application
├── shinobi_client.py      # Shinobi API integration
├── onvif_events.py        # ONVIF event monitoring
├── event_trigger.py       # Manual event trigger tool
├── test_setup.py          # Setup verification script
├── config.json            # Configuration file
├── requirements.txt       # Python dependencies
├── README.md              # Integration guide
├── SETUP_GUIDE.md         # This file
├── camera_server.log      # Server logs
└── recordings/            # Video recordings directory
    └── cam1/
        └── 2024-01-15/
            └── 14/
                ├── segment_14-30-00.mp4
                ├── segment_14-30-00.json
                ├── pre_event_14-35-22.mp4
                └── pre_event_14-35-22.json
```

## Recording Structure

Recordings are organized by:
- Camera ID
- Date (YYYY-MM-DD)
- Hour (HH)

### Recording Types

1. **Continuous Segments** (`segment_*.mp4`)
   - 60-second continuous recordings
   - Created every minute
   - Metadata in accompanying `.json` file

2. **Pre-Event Buffer** (`pre_event_*.mp4`)
   - 60 seconds before event trigger
   - Saved when event is detected
   - Contains buffered frames

3. **Event Recording**
   - Continues for 60 seconds after event
   - Triggered by ONVIF events or HTTP API

## API Endpoints

### POST /api/events/motion
Trigger motion detection event

**Request:**
```json
{
  "camera_id": "cam1",
  "event_type": "motion",
  "timestamp": 1640995200.0,
  "metadata": {
    "source": "external_system",
    "confidence": 0.95
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Motion event triggered for cam1"
}
```

### POST /api/events/alarm
Trigger alarm event

**Request:**
```json
{
  "camera_id": "cam1",
  "event_type": "alarm",
  "alarm_type": "general",
  "timestamp": 1640995200.0
}
```

### GET /api/status
Get server status

**Response:**
```json
{
  "running": true,
  "cameras": 1,
  "camera_ids": ["cam1"]
}
```

## Integration with RPOS

See `README.md` for detailed integration instructions with RPOS ONVIF server.

## Logs

Server logs are written to:
- `camera_server.log` - Main application log
- Rotated daily, kept for 7 days

View logs:
```bash
tail -f camera_server.log
```

## Support

For issues or questions:
1. Check logs: `tail -f camera_server.log`
2. Verify configuration: `python3 test_setup.py`
3. Test individual components (RTSP, ONVIF, Shinobi)
