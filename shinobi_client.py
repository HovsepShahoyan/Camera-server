import requests
import json
import asyncio
from loguru import logger
from urllib.parse import quote


class ShinobiClient:
    def __init__(self, base_url, api_key, group_key):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.group_key = group_key
        self.session = requests.Session()

    def _make_request(self, method, endpoint, data=None, params=None):
        """Make authenticated request to Shinobi API"""
        url = "{}{}".format(self.base_url, endpoint)

        headers = {
            'Content-Type': 'application/json'
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

            logger.debug("Request URL: {} | Method: {} | Status: {}".format(
                response.url, method, response.status_code))

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error("Shinobi API request failed: {} | URL: {}".format(e, url))
            return None

    async def add_monitor(self, monitor_id, config):
        endpoint = "/{}/configureMonitor/{}/{}".format(
            self.api_key, 
            self.group_key, 
            monitor_id
        )

        monitor_config = {
            'mid': monitor_id,
            'ke': self.group_key,
            'name': config['name'],
            'type': config.get('type', 'h264'),
            'protocol': 'rtsp',
            'host': config['host'],
            'port': str(config.get('port', 554)),
            'path': config.get('path', '/stream'),
            'mode': config.get('mode', 'record'),
            'details': json.dumps({
                'rtsp_transport': 'tcp',
                'skip_ping': True,
                'fatal_max': 10,
                'detector': '1',
                'detector_record_method': 'sip',
                'detector_trigger': '1',
                'detector_timeout': 10,
                'record_method': 'all',
                'recording_dir': './recordings/{}'.format(monitor_id)
            })
        }

        params = {
            'data': json.dumps(monitor_config)
        }

        result = self._make_request('POST', endpoint, params=params)
        if result and result.get('ok'):
            logger.info("Successfully added monitor {} to Shinobi".format(monitor_id))
            return True
        else:
            logger.error("Failed to add monitor {} to Shinobi. Response: {}".format(monitor_id, result))
            return False

    async def update_monitor_mode(self, monitor_id, mode):
        endpoint = "/{}/monitor/{}/{}/{}".format(
            self.api_key, 
            self.group_key, 
            monitor_id,
            mode
        )

        result = self._make_request('GET', endpoint)
        if result and result.get('ok'):
            logger.info("Successfully updated monitor {} mode to {}".format(monitor_id, mode))
            return True
        else:
            logger.error("Failed to update monitor {} mode. Response: {}".format(monitor_id, result))
            return False

    async def trigger_event_recording(self, monitor_id):
        endpoint = "/{}/motion/{}/{}".format(
            self.api_key, 
            self.group_key, 
            monitor_id
        )

        trigger_data = {
            'plug': monitor_id,
            'name': 'External Event',
            'reason': 'ONVIF Event Triggered',
            'confidence': 100
        }

        params = {
            'data': json.dumps(trigger_data)
        }

        result = self._make_request('GET', endpoint, params=params)
        if result and result.get('ok'):
            logger.info("Successfully triggered event recording for monitor {}".format(monitor_id))
            return True
        else:
            logger.error("Failed to trigger event recording for monitor {}. Response: {}".format(monitor_id, result))
            return False

    async def get_monitors(self):
        endpoint = "/{}/monitor/{}".format(self.api_key, self.group_key)

        result = self._make_request('GET', endpoint)
        if result:
            return result
        else:
            logger.error("Failed to get monitors")
            return None

    async def get_monitor_status(self, monitor_id):
        endpoint = "/{}/monitor/{}".format(self.api_key, self.group_key)

        result = self._make_request('GET', endpoint)
        if result:
            monitors = result if isinstance(result, list) else result.get('monitors', result)
            if isinstance(monitors, list):
                for monitor in monitors:
                    if monitor.get('mid') == monitor_id:
                        return monitor
            logger.warning("Monitor {} not found in status".format(monitor_id))
            return None
        else:
            logger.error("Failed to get status for monitor {}".format(monitor_id))
            return None

    async def delete_monitor(self, monitor_id):
        endpoint = "/{}/configureMonitor/{}/{}/delete".format(
            self.api_key, 
            self.group_key, 
            monitor_id
        )

        result = self._make_request('GET', endpoint)
        if result and result.get('ok'):
            logger.info("Successfully deleted monitor {}".format(monitor_id))
            return True
        else:
            logger.error("Failed to delete monitor {}. Response: {}".format(monitor_id, result))
            return False

    async def get_recordings(self, monitor_id, start_date=None, end_date=None):
        endpoint = "/{}/videos/{}/{}".format(
            self.api_key, 
            self.group_key,
            monitor_id
        )

        params = {}
        if start_date:
            params['start'] = start_date
        if end_date:
            params['end'] = end_date

        result = self._make_request('GET', endpoint, params=params)
        if result:
            videos = result.get('videos', result) if isinstance(result, dict) else result
            return videos
        else:
            logger.error("Failed to get recordings for monitor {}".format(monitor_id))
            return None

    async def download_recording(self, monitor_id, filename, save_path):
        endpoint = "/{}/videos/{}/{}/{}".format(
            self.api_key, 
            self.group_key, 
            monitor_id,
            filename
        )

        try:
            response = self.session.get(
                "{}{}".format(self.base_url, endpoint),
                stream=True
            )
            response.raise_for_status()

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info("Successfully downloaded recording {} to {}".format(filename, save_path))
            return True

        except Exception as e:
            logger.error("Failed to download recording {}: {}".format(filename, e))
            return False

    async def probe_camera(self, rtsp_url):
        endpoint = "/{}/probe/{}".format(self.api_key, self.group_key)
        
        params = {
            'url': rtsp_url,
            'flags': 'default'
        }

        result = self._make_request('GET', endpoint, params=params)
        if result:
            logger.info("Successfully probed camera URL")
            return result
        else:
            logger.error("Failed to probe camera URL: {}".format(rtsp_url))
            return None
