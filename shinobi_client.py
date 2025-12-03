import requests
import json
import asyncio
from loguru import logger

class ShinobiClient:
    def __init__(self, base_url, api_key, group_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.group_key = group_key
        self.session = requests.Session()

    def _make_request(self, method, endpoint, data=None):
        """Make authenticated request to Shinobi API"""
        url = "{}{}".format(self.base_url, endpoint)

        headers = {
            'Content-Type': 'application/json'
        }

        params = {
            'key': self.api_key,
            'group': self.group_key
        }

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, params=params, json=data)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, headers=headers, params=params)
            else:
                raise ValueError("Unsupported HTTP method: {}".format(method))

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error("Shinobi API request failed: {}".format(e))
            return None

    async def add_monitor(self, monitor_id, config):
        """Add a new monitor to Shinobi"""
        endpoint = "/api/{}/configureMonitor/{}".format(self.group_key, monitor_id)

        monitor_config = {
            'name': config['name'],
            'mode': config.get('mode', 'record'),
            'type': config.get('type', 'rtsp'),
            'host': config['host'],
            'port': config.get('port', 554),
            'path': config.get('path', '/stream'),
            'details': {
                'rtsp_transport': 'tcp',
                'skip_ping': True,
                'fatal_max': 10,
                'detector': '1',
                'detector_record_method': 'sip',
                'detector_trigger': '1',
                'detector_timeout': 10,
                'record_method': 'all',
                'recording_dir': './recordings/{}'.format(monitor_id)
            }
        }

        result = self._make_request('POST', endpoint, monitor_config)
        if result and result.get('ok'):
            logger.info("Successfully added monitor {} to Shinobi".format(monitor_id))
            return True
        else:
            logger.error("Failed to add monitor {} to Shinobi".format(monitor_id))
            return False

    async def update_monitor_mode(self, monitor_id, mode):
        """Update monitor recording mode"""
        endpoint = "/api/{}/monitor/{}".format(self.group_key, monitor_id)

        update_data = {
            'mode': mode
        }

        result = self._make_request('POST', endpoint, update_data)
        if result and result.get('ok'):
            logger.info("Successfully updated monitor {} mode to {}".format(monitor_id, mode))
            return True
        else:
            logger.error("Failed to update monitor {} mode".format(monitor_id))
            return False

    async def trigger_event_recording(self, monitor_id):
        """Trigger event-based recording for a monitor"""
        endpoint = "/api/{}/motion/{}".format(self.group_key, monitor_id)

        trigger_data = {
            'name': 'External Event',
            'reason': 'ONVIF Event Triggered',
            'confidence': 100
        }

        result = self._make_request('POST', endpoint, trigger_data)
        if result and result.get('ok'):
            logger.info("Successfully triggered event recording for monitor {}".format(monitor_id))
            return True
        else:
            logger.error("Failed to trigger event recording for monitor {}".format(monitor_id))
            return False

    async def get_monitor_status(self, monitor_id):
        """Get monitor status"""
        endpoint = "/api/{}/monitor/{}".format(self.group_key, monitor_id)

        result = self._make_request('GET', endpoint)
        if result and result.get('ok'):
            return result
        else:
            logger.error("Failed to get status for monitor {}".format(monitor_id))
            return None

    async def delete_monitor(self, monitor_id):
        """Delete a monitor from Shinobi"""
        endpoint = "/api/{}/configureMonitor/{}".format(self.group_key, monitor_id)

        result = self._make_request('DELETE', endpoint)
        if result and result.get('ok'):
            logger.info("Successfully deleted monitor {}".format(monitor_id))
            return True
        else:
            logger.error("Failed to delete monitor {}".format(monitor_id))
            return False

    async def get_recordings(self, monitor_id, start_date=None, end_date=None):
        """Get recordings for a monitor"""
        endpoint = "/api/{}/videos/{}".format(self.group_key, monitor_id)

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        result = self._make_request('GET', endpoint)
        if result and result.get('ok'):
            return result.get('videos', [])
        else:
            logger.error("Failed to get recordings for monitor {}".format(monitor_id))
            return None

    async def download_recording(self, monitor_id, filename, save_path):
        """Download a specific recording"""
        endpoint = "/api/{}/videos/{}/{}".format(self.group_key, monitor_id, filename)

        try:
            response = self.session.get("{}{}".format(self.base_url, endpoint),
                                      params={'key': self.api_key, 'group': self.group_key},
                                      stream=True)
            response.raise_for_status()

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info("Successfully downloaded recording {} to {}".format(filename, save_path))
            return True

        except Exception as e:
            logger.error("Failed to download recording {}: {}".format(filename, e))
            return False
