#!/usr/bin/env python3
"""
Event trigger script to send events from RPOS ONVIF server to camera_server.
This simulates motion detection events that would normally come from cameras.
"""

import requests
import json
import time
import argparse

class EventTrigger:
    def __init__(self, camera_server_url="http://localhost:8555"):
        self.camera_server_url = camera_server_url.rstrip('/')

    def trigger_motion_event(self, camera_id):
        """Trigger a motion detection event for a specific camera"""
        endpoint = "{}/api/events/motion".format(self.camera_server_url)

        payload = {
            "camera_id": camera_id,
            "event_type": "motion",
            "timestamp": time.time(),
            "metadata": {
                "source": "rpos_simulator",
                "confidence": 0.95
            }
        }

        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()

            print("✅ Motion event triggered for camera {}".format(camera_id))
            return True

        except requests.exceptions.RequestException as e:
            print("❌ Failed to trigger motion event: {}".format(e))
            return False

    def trigger_alarm_event(self, camera_id, alarm_type="general"):
        """Trigger an alarm event for a specific camera"""
        endpoint = "{}/api/events/alarm".format(self.camera_server_url)

        payload = {
            "camera_id": camera_id,
            "event_type": "alarm",
            "alarm_type": alarm_type,
            "timestamp": time.time(),
            "metadata": {
                "source": "rpos_simulator",
                "severity": "high"
            }
        }

        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()

            print("✅ Alarm event triggered for camera {} ({})".format(camera_id, alarm_type))
            return True

        except requests.exceptions.RequestException as e:
            print("❌ Failed to trigger alarm event: {}".format(e))
            return False

def main():
    parser = argparse.ArgumentParser(description="Trigger events to camera_server")
    parser.add_argument("--server", default="http://localhost:8555",
                       help="Camera server URL (default: http://localhost:8555)")
    parser.add_argument("--camera", required=True,
                       help="Camera ID to trigger event for")
    parser.add_argument("--event", choices=["motion", "alarm"],
                       default="motion", help="Event type (default: motion)")
    parser.add_argument("--alarm-type", default="general",
                       help="Alarm type if event is alarm (default: general)")
    parser.add_argument("--interval", type=float, default=0,
                       help="Interval in seconds between repeated events (0 = single event)")

    args = parser.parse_args()

    trigger = EventTrigger(args.server)

    if args.interval > 0:
        print("🔄 Triggering {} events for camera {} every {}s...".format(args.event, args.camera, args.interval))
        print("Press Ctrl+C to stop")

        try:
            while True:
                if args.event == "motion":
                    trigger.trigger_motion_event(args.camera)
                else:
                    trigger.trigger_alarm_event(args.camera, args.alarm_type)

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n🛑 Stopped triggering events")

    else:
        # Single event
        if args.event == "motion":
            success = trigger.trigger_motion_event(args.camera)
        else:
            success = trigger.trigger_alarm_event(args.camera, args.alarm_type)

        exit(0 if success else 1)

if __name__ == "__main__":
    main()
