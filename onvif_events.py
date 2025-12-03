import asyncio
from onvif import ONVIFCamera
from zeep import Client
from zeep.transports import Transport
from loguru import logger
import time

class ONVIFEventSubscriber:
    def __init__(self, camera_config):
        self.camera_id = camera_config['id']
        self.ip = camera_config['onvif_url'].split('//')[1].split(':')[0]
        self.port = int(camera_config['onvif_url'].split(':')[-1].split('/')[0])
        self.username = camera_config['username']
        self.password = camera_config['password']
        self.camera = None
        self.events_service = None
        self.pull_point_subscription = None
        self.is_connected = False

    async def connect(self):
        """Connect to ONVIF camera"""
        try:
            transport = Transport(timeout=10)
            self.camera = ONVIFCamera(self.ip, self.port, self.username, self.password, transport=transport)

            # Create media service
            self.camera.create_media_service()
            self.camera.create_ptz_service()
            self.camera.create_events_service()

            self.events_service = self.camera.create_events_service()
            self.is_connected = True
            logger.info(f"Connected to ONVIF camera {self.camera_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to ONVIF camera {self.camera_id}: {e}")
            return False

    async def subscribe_to_events(self, callback):
        """Subscribe to motion detection events"""
        if not self.is_connected:
            return False

        try:
            # Create pull point subscription for events
            subscription = self.events_service.CreatePullPointSubscription()

            # Get the subscription reference
            subscription_ref = subscription.SubscriptionReference.Address._value_1

            # Set up event filter for motion detection
            event_filter = {
                'TopicExpression': {
                    'Dialect': 'http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet',
                    'MessageContent': [
                        'tns1:RuleEngine/CellMotionDetector/Motion',
                        'tns1:VideoSource/MotionAlarm',
                        'tns1:Device/Trigger/DigitalInput'
                    ]
                }
            }

            # Subscribe to events
            self.pull_point_subscription = self.events_service.PullMessages(
                SubscriptionReference={'Address': subscription_ref},
                MessageLimit=10,
                Timeout='PT30S'
            )

            logger.info(f"Subscribed to events for camera {self.camera_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to events for camera {self.camera_id}: {e}")
            return False

    async def poll_events(self, callback):
        """Poll for events continuously"""
        while self.is_connected:
            try:
                if self.pull_point_subscription:
                    # Pull messages
                    messages = self.events_service.PullMessages(
                        SubscriptionReference=self.pull_point_subscription.SubscriptionReference,
                        MessageLimit=10,
                        Timeout='PT10S'
                    )

                    if messages and messages.NotificationMessage:
                        for message in messages.NotificationMessage:
                            # Check if it's a motion event
                            topic = message.Topic._value_1 if hasattr(message.Topic, '_value_1') else str(message.Topic)

                            if any(keyword in topic for keyword in ['Motion', 'motion', 'Alarm']):
                                logger.info(f"Motion detected on camera {self.camera_id}")
                                await callback(self.camera_id, 'motion', message)

                await asyncio.sleep(1)  # Poll every second

            except Exception as e:
                logger.error(f"Error polling events for camera {self.camera_id}: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def disconnect(self):
        """Disconnect from camera"""
        if self.pull_point_subscription:
            try:
                self.events_service.Unsubscribe(self.pull_point_subscription.SubscriptionReference)
            except:
                pass

        self.is_connected = False
        logger.info(f"Disconnected from ONVIF camera {self.camera_id}")

class ONVIFManager:
    def __init__(self):
        self.subscribers = {}
        self.event_callback = None

    def set_event_callback(self, callback):
        """Set callback for event notifications"""
        self.event_callback = callback

    async def add_camera(self, camera_config):
        """Add a camera for event monitoring"""
        subscriber = ONVIFEventSubscriber(camera_config)
        if await subscriber.connect():
            if await subscriber.subscribe_to_events(self.event_callback):
                self.subscribers[camera_config['id']] = subscriber
                return True
        return False

    async def start_monitoring(self):
        """Start monitoring all cameras for events"""
        tasks = []
        for subscriber in self.subscribers.values():
            task = asyncio.create_task(subscriber.poll_events(self.event_callback))
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_monitoring(self):
        """Stop monitoring and disconnect all cameras"""
        for subscriber in self.subscribers.values():
            await subscriber.disconnect()
        self.subscribers.clear()
