#!/usr/bin/env python3
import asyncio
import cv2
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from datetime import datetime, timedelta
from loguru import logger
from aiohttp import web

from shinobi_client import ShinobiClient
from onvif_events import ONVIFManager

class StreamProcessor:
    def __init__(self, camera_id, rtsp_url, recording_config):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.config = recording_config

        # Recording state
        self.is_recording = False
        self.event_recording = False
        self.event_end_time = None

        # Buffers
        # Reduce buffer size for lower RAM usage (e.g., 10 seconds at 10 FPS)
        self.frame_buffer = deque(maxlen=int(10 * 10))  # 10 seconds at 10 FPS
        self.segment_start_time = None
        self.video_writer = None
        self.segment_file_path = None

        # Threading
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.running = False

        # Limit FPS to 30 FPS for recording
        self.max_fps = 30

    async def start_processing(self):
        """Start processing the RTSP stream"""
        self.running = True
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                logger.info(f"Opening RTSP stream for camera {self.camera_id}: {self.rtsp_url}")

                # Use ffmpeg options for hardware decoding if supported
                # OpenCV does not allow direct passing of ffmpeg options, but you can try appending options to the URL
                # Example: 'rtsp_transport;tcp' or use ffmpeg directly for full control

                # If you want full GPU decoding, consider using ffmpeg via subprocess:
                # ffmpeg -hwaccel cuda -c:v h264_cuvid -i <rtsp_url> ...

                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                # If you have OpenCV >= 4.5.1, you can set options:
                # cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                # cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)

                if not cap.isOpened():
                    logger.error(f"Failed to open RTSP stream for camera {self.camera_id} (URL: {self.rtsp_url})")
                    await asyncio.sleep(5)
                    continue

                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                # Limit FPS to max_fps
                fps = min(fps, self.max_fps)
                frame_interval = 1.0 / fps

                logger.info(f"Started processing camera {self.camera_id} at {fps} FPS")

                self.segment_start_time = time.time()
                first_frame = None

                while self.running and cap.isOpened():
                    start_time = time.time()

                    ret, frame = cap.read()
                    if not ret:
                        logger.warning(f"Failed to read frame from camera {self.camera_id} (URL: {self.rtsp_url})")
                        break

                    # On first frame, start the segment writer with correct size
                    if first_frame is None:
                        first_frame = frame
                        self._start_new_segment_writer(fps, frame)

                    # Add to rolling buffer
                    self.frame_buffer.append((time.time(), frame))

                    # Write frame directly to disk for continuous recording
                    if self.video_writer is not None:
                        self.video_writer.write(frame)
                        # Explicitly delete frame reference
                        del frame

                    # Log ThreadPoolExecutor queue size
                    logger.info(f"ThreadPoolExecutor queue size: {self.executor._work_queue.qsize()}")

                    # Check if segment is complete (1 minute)
                    if time.time() - self.segment_start_time >= self.config['segment_duration']:
                        self._close_segment_writer()
                        self.segment_start_time = time.time()
                        first_frame = None  # Reset for next segment

                    # Handle event recording (still uses buffer)
                    await self._handle_event_recording(frame, fps)

                    # Maintain frame rate
                    elapsed = time.time() - start_time
                    sleep_time = max(0, frame_interval - elapsed)
                    await asyncio.sleep(sleep_time)

                self._close_segment_writer()
                cap.release()

            except Exception as e:
                logger.error(f"Error processing camera {self.camera_id}: {e}")
                await asyncio.sleep(5)

    async def _handle_event_recording(self, frame, fps):
        """Handle event-based recording"""
        if self.event_recording:
            current_time = time.time()

            if current_time >= self.event_end_time:
                # Event recording finished
                self.event_recording = False
                self.event_end_time = None
                logger.info(f"Event recording finished for camera {self.camera_id}")
                self.current_segment_frames = []  # Clear buffer after event
            else:
                # Continue recording event
                self.current_segment_frames.append(frame)
                # Limit event buffer size
                if len(self.current_segment_frames) > 300:  # e.g., max 10 seconds at 30 FPS
                    self.current_segment_frames.pop(0)
                # Log buffer size for debugging
                if len(self.current_segment_frames) % 100 == 0:
                    logger.info(f"event current_segment_frames size for {self.camera_id}: {len(self.current_segment_frames)}")

    def trigger_event_recording(self):
        """Trigger event recording (1 min before + during + 1 min after)"""
        current_time = time.time()
        self.event_end_time = current_time + self.config['post_event_duration']
        self.event_recording = True

        # Save pre-event buffer
        self.executor.submit(self._save_pre_event_buffer, current_time)

        logger.info(f"Event recording triggered for camera {self.camera_id}")

    def _save_pre_event_buffer(self, trigger_time):
        """Save the 1-minute pre-event buffer"""
        logger.info(f"Attempting to save pre-event buffer for camera {self.camera_id}")
        try:
            timestamp = datetime.fromtimestamp(trigger_time)
            date_dir = timestamp.strftime("%Y-%m-%d")
            hour_dir = timestamp.strftime("%H")

            base_dir = os.path.join(self.config['base_dir'], self.camera_id, date_dir, hour_dir)
            os.makedirs(base_dir, exist_ok=True)

            filename = f"pre_event_{timestamp.strftime('%H-%M-%S')}.mp4"
            filepath = os.path.join(base_dir, filename)

            # Convert buffer to video
            if self.frame_buffer:
                frames = [frame for _, frame in self.frame_buffer]
                height, width = frames[0].shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(filepath, fourcc, 30, (width, height))

                for frame in frames:
                    out.write(frame)
                    del frame
                out.release()

                # Save metadata
                metadata = {
                    'camera_id': self.camera_id,
                    'type': 'pre_event',
                    'start_time': trigger_time - self.config['pre_event_buffer'],
                    'end_time': trigger_time,
                    'duration': self.config['pre_event_buffer'],
                    'file': filename
                }

                metadata_file = filepath.replace('.mp4', '.json')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

                logger.info(f"Saved pre-event buffer: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save pre-event buffer for camera {self.camera_id}: {e}")

    def _start_new_segment_writer(self, fps, frame):
        """Start a new video writer for the next segment using the frame's size"""
        timestamp = datetime.fromtimestamp(self.segment_start_time)
        date_dir = timestamp.strftime("%Y-%m-%d")
        hour_dir = timestamp.strftime("%H")
        base_dir = os.path.join(self.config['base_dir'], self.camera_id, date_dir, hour_dir)
        os.makedirs(base_dir, exist_ok=True)
        filename = f"segment_{timestamp.strftime('%H-%M-%S')}.mp4"
        self.segment_file_path = os.path.join(base_dir, filename)

        height, width = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(self.segment_file_path, fourcc, fps, (width, height))
        logger.info(f"Started new segment file: {self.segment_file_path}")

    def _close_segment_writer(self):
        """Close the current video writer and save metadata"""
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
            # Save metadata
            metadata = {
                'camera_id': self.camera_id,
                'type': 'continuous',
                'start_time': self.segment_start_time,
                'end_time': time.time(),
                'duration': time.time() - self.segment_start_time,
                'file': os.path.basename(self.segment_file_path)
            }
            metadata_file = self.segment_file_path.replace('.mp4', '.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Closed segment file: {self.segment_file_path}")
            self.segment_file_path = None

    async def stop(self):
        """Stop processing"""
        self.running = False
        self.executor.shutdown(wait=True)

class CameraServer:
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.shinobi = ShinobiClient(
            self.config['shinobi']['base_url'],
            self.config['shinobi']['api_key'],
            self.config['shinobi']['group_key']
        )

        self.onvif_manager = ONVIFManager()
        self.stream_processors = {}
        self.running = False

        # Set up HTTP server
        self.app = web.Application()
        self.app.router.add_post('/api/events/motion', self.handle_motion_event)
        self.app.router.add_post('/api/events/alarm', self.handle_alarm_event)
        self.app.router.add_get('/api/status', self.handle_status)

        # Set up logging
        logger.add("camera_server.log", rotation="1 day", retention="7 days")

    async def initialize_cameras(self):
        """Initialize all cameras and set up processors"""
        for camera in self.config['cameras']:
            monitor_config = {
                'name': camera['name'],
                'host': camera['rtsp_url'].split('@')[1].split(':')[0] if '@' in camera['rtsp_url'] else camera['rtsp_url'].split('//')[1].split(':')[0],
                'port': 554,
                'path': '/' + camera['rtsp_url'].split('/')[-1]
            }

            # Try to add monitor to Shinobi, log result
            shinobi_success = await self.shinobi.add_monitor(camera['id'], monitor_config)
            if shinobi_success:
                logger.info(f"Shinobi monitor created for {camera['id']}")
                # Optionally, set monitor mode to 'record'
                await self.shinobi.update_monitor_mode(camera['id'], 'record')
            else:
                logger.warning(f"Shinobi monitor creation failed for {camera['id']}")

            # Always create stream processor
            processor = StreamProcessor(
                camera['id'],
                camera['rtsp_url'],
                self.config['recording']
            )
            self.stream_processors[camera['id']] = processor

            # Set up ONVIF event monitoring
            await self.onvif_manager.add_camera(camera)

        self.onvif_manager.set_event_callback(self._on_event_detected)

    async def handle_motion_event(self, request):
        """Handle motion event from HTTP API"""
        try:
            data = await request.json()
            camera_id = data.get('camera_id')
            
            if camera_id in self.stream_processors:
                self.stream_processors[camera_id].trigger_event_recording()
                shinobi_result = await self.shinobi.trigger_event_recording(camera_id)
                if shinobi_result:
                    logger.info(f"Shinobi event recording triggered for {camera_id}")
                else:
                    logger.warning(f"Shinobi event trigger failed for {camera_id}")
                logger.info(f"Motion event triggered via API for camera {camera_id}")
                return web.json_response({'status': 'success', 'message': f'Motion event triggered for {camera_id}'})
            else:
                return web.json_response({'status': 'error', 'message': f'Camera {camera_id} not found'}, status=404)
        except Exception as e:
            logger.error(f"Error handling motion event: {e}")
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)

    async def handle_alarm_event(self, request):
        """Handle alarm event from HTTP API"""
        try:
            data = await request.json()
            camera_id = data.get('camera_id')
            
            if camera_id in self.stream_processors:
                self.stream_processors[camera_id].trigger_event_recording()
                shinobi_result = await self.shinobi.trigger_event_recording(camera_id)
                if shinobi_result:
                    logger.info(f"Shinobi event recording triggered for {camera_id}")
                else:
                    logger.warning(f"Shinobi event trigger failed for {camera_id}")
                logger.info(f"Alarm event triggered via API for camera {camera_id}")
                return web.json_response({'status': 'success', 'message': f'Alarm event triggered for {camera_id}'})
            else:
                return web.json_response({'status': 'error', 'message': f'Camera {camera_id} not found'}, status=404)
        except Exception as e:
            logger.error(f"Error handling alarm event: {e}")
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)

    async def handle_status(self, request):
        """Handle status request from HTTP API"""
        try:
            status = {
                'running': self.running,
                'cameras': len(self.stream_processors),
                'camera_ids': list(self.stream_processors.keys())
            }
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error handling status request: {e}")
            return web.json_response({'status': 'error', 'message': str(e)}, status=500)

    async def _on_event_detected(self, camera_id, event_type, event_data):
        """Handle ONVIF event detection"""
        if camera_id in self.stream_processors:
            logger.info(f"Event detected on camera {camera_id}: {event_type}")
            self.stream_processors[camera_id].trigger_event_recording()
            shinobi_result = await self.shinobi.trigger_event_recording(camera_id)
            if shinobi_result:
                logger.info(f"Shinobi event recording triggered for {camera_id} (ONVIF)")
            else:
                logger.warning(f"Shinobi event trigger failed for {camera_id} (ONVIF)")

    async def start_server(self):
        """Start the camera server"""
        logger.info("Starting Camera Server...")

        # Initialize cameras
        await self.initialize_cameras()

        # Start stream processors
        tasks = []
        for processor in self.stream_processors.values():
            task = asyncio.create_task(processor.start_processing())
            tasks.append(task)

        # Start ONVIF monitoring
        onvif_task = asyncio.create_task(self.onvif_manager.start_monitoring())
        tasks.append(onvif_task)

        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config['server']['host'], self.config['server']['port'])
        await site.start()
        logger.info(f"HTTP server started on {self.config['server']['host']}:{self.config['server']['port']}")

        self.running = True
        logger.info(f"Camera server started with {len(self.stream_processors)} cameras")
        
        if len(self.stream_processors) == 0:
            logger.warning("No cameras initialized. Server will run with HTTP API only.")

        try:
            # Keep server running indefinitely for HTTP API
            logger.info("Server running. Press Ctrl+C to stop.")
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down camera server...")
        except Exception as e:
            logger.error(f"Unexpected error in server: {e}")
        finally:
            await runner.cleanup()
            await self.stop_server()

    async def stop_server(self):
        """Stop the camera server"""
        self.running = False

        # Stop all processors
        for processor in self.stream_processors.values():
            await processor.stop()

        # Stop ONVIF monitoring
        await self.onvif_manager.stop_monitoring()

        logger.info("Camera server stopped")
async def main():
    server = CameraServer()
    await server.start_server()

if __name__ == "__main__":
    asyncio.run(main())
