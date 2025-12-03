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
        self.frame_buffer = deque(maxlen=int(recording_config['pre_event_buffer'] * 30))  # 30 FPS assumption
        self.current_segment_frames = []
        self.segment_start_time = None

        # Threading
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.running = False

    async def start_processing(self):
        """Start processing the RTSP stream"""
        self.running = True
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                # Open RTSP stream
                cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                if not cap.isOpened():
                    logger.error(f"Failed to open RTSP stream for camera {self.camera_id}")
                    await asyncio.sleep(5)
                    continue

                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                frame_interval = 1.0 / fps

                logger.info(f"Started processing camera {self.camera_id} at {fps} FPS")

                while self.running and cap.isOpened():
                    start_time = time.time()

                    ret, frame = cap.read()
                    if not ret:
                        logger.warning(f"Failed to read frame from camera {self.camera_id}")
                        break

                    # Add to rolling buffer
                    self.frame_buffer.append((time.time(), frame))

                    # Handle continuous recording
                    await self._handle_continuous_recording(frame, fps)

                    # Handle event recording
                    await self._handle_event_recording(frame, fps)

                    # Maintain frame rate
                    elapsed = time.time() - start_time
                    sleep_time = max(0, frame_interval - elapsed)
                    await asyncio.sleep(sleep_time)

                cap.release()

            except Exception as e:
                logger.error(f"Error processing camera {self.camera_id}: {e}")
                await asyncio.sleep(5)

    async def _handle_continuous_recording(self, frame, fps):
        """Handle continuous 1-minute recording segments"""
        current_time = time.time()

        if self.segment_start_time is None:
            self.segment_start_time = current_time
            self.current_segment_frames = []

        self.current_segment_frames.append(frame)

        # Check if segment is complete (1 minute)
        if current_time - self.segment_start_time >= self.config['segment_duration']:
            # Save segment in background
            segment_frames = self.current_segment_frames.copy()
            segment_start = self.segment_start_time
            self.executor.submit(self._save_segment, segment_frames, segment_start, fps)

            # Reset for next segment
            self.segment_start_time = current_time
            self.current_segment_frames = []

    async def _handle_event_recording(self, frame, fps):
        """Handle event-based recording"""
        if self.event_recording:
            current_time = time.time()

            if current_time >= self.event_end_time:
                # Event recording finished
                self.event_recording = False
                self.event_end_time = None
                logger.info(f"Event recording finished for camera {self.camera_id}")
            else:
                # Continue recording event
                self.current_segment_frames.append(frame)

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

    def _save_segment(self, frames, start_time, fps):
        """Save a recording segment"""
        try:
            timestamp = datetime.fromtimestamp(start_time)
            date_dir = timestamp.strftime("%Y-%m-%d")
            hour_dir = timestamp.strftime("%H")

            base_dir = os.path.join(self.config['base_dir'], self.camera_id, date_dir, hour_dir)
            os.makedirs(base_dir, exist_ok=True)

            filename = f"segment_{timestamp.strftime('%H-%M-%S')}.mp4"
            filepath = os.path.join(base_dir, filename)

            if frames:
                height, width = frames[0].shape[:2]
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

                for frame in frames:
                    out.write(frame)
                out.release()

                # Save metadata
                metadata = {
                    'camera_id': self.camera_id,
                    'type': 'continuous',
                    'start_time': start_time,
                    'end_time': start_time + len(frames) / fps,
                    'duration': len(frames) / fps,
                    'file': filename
                }

                metadata_file = filepath.replace('.mp4', '.json')
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

                logger.info(f"Saved segment: {filepath}")

        except Exception as e:
            logger.error(f"Failed to save segment for camera {self.camera_id}: {e}")

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

        # Set up logging
        logger.add("camera_server.log", rotation="1 day", retention="7 days")

    async def initialize_cameras(self):
        """Initialize all cameras in Shinobi and set up processors"""
        for camera in self.config['cameras']:
            # Add monitor to Shinobi
            monitor_config = {
                'name': camera['name'],
                'host': camera['rtsp_url'].split('@')[1].split(':')[0] if '@' in camera['rtsp_url'] else camera['rtsp_url'].split('//')[1].split(':')[0],
                'port': 554,
                'path': '/' + camera['rtsp_url'].split('/')[-1]
            }

            success = await self.shinobi.add_monitor(camera['id'], monitor_config)
            if success:
                # Create stream processor
                processor = StreamProcessor(
                    camera['id'],
                    camera['rtsp_url'],
                    self.config['recording']
                )
                self.stream_processors[camera['id']] = processor

                # Set up ONVIF event monitoring
                await self.onvif_manager.add_camera(camera)

        # Set event callback
        self.onvif_manager.set_event_callback(self._on_event_detected)

    async def _on_event_detected(self, camera_id, event_type, event_data):
        """Handle ONVIF event detection"""
        if camera_id in self.stream_processors:
            logger.info(f"Event detected on camera {camera_id}: {event_type}")
            self.stream_processors[camera_id].trigger_event_recording()

            # Also trigger in Shinobi
            await self.shinobi.trigger_event_recording(camera_id)

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

        self.running = True
        logger.info(f"Camera server started with {len(self.stream_processors)} cameras")

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("Shutting down camera server...")
        finally:
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
