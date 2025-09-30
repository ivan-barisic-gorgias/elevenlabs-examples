import asyncio
import base64
import json
from fastapi import WebSocket
from elevenlabs.conversational_ai.conversation import AudioInterface
from starlette.websockets import WebSocketDisconnect, WebSocketState


class TwilioAudioInterface(AudioInterface):
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.input_callback = None
        self.stream_sid = None
        self.loop = asyncio.get_event_loop()

    def start(self, input_callback):
        self.input_callback = input_callback

    def stop(self):
        self.input_callback = None
        self.stream_sid = None

    def output(self, audio: bytes):
        """
        This method should return quickly and not block the calling thread.
        """
        asyncio.run_coroutine_threadsafe(self.send_audio_to_twilio(audio), self.loop)

    def interrupt(self):
        asyncio.run_coroutine_threadsafe(self.send_clear_message_to_twilio(), self.loop)

    async def send_audio_to_twilio(self, audio: bytes):
        if self.stream_sid:
            try:
                audio_payload = base64.b64encode(audio).decode("utf-8")
                audio_delta = {
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": audio_payload},
                }
                if self.websocket.application_state == WebSocketState.CONNECTED:
                    await self.websocket.send_text(json.dumps(audio_delta))
                    print(f"Sent audio to Twilio: {len(audio)} bytes")
                else:
                    print(f"WebSocket not connected, state: {self.websocket.application_state}")
            except WebSocketDisconnect as e:
                print(f"WebSocket disconnected while sending audio: {e}")
            except RuntimeError as e:
                print(f"Runtime error while sending audio: {e}")
            except Exception as e:
                print(f"Unexpected error sending audio: {type(e).__name__}: {e}")
                print("Attempting retry for audio send...")
                try:
                    if self.websocket.application_state == WebSocketState.CONNECTED:
                        await self.websocket.send_text(json.dumps(audio_delta))
                        print(f"Retry successful - Sent audio to Twilio: {len(audio)} bytes")
                    else:
                        print(f"Retry failed - WebSocket still not connected, state: {self.websocket.application_state}")
                except Exception as retry_e:
                    print(f"Retry failed for audio send: {type(retry_e).__name__}: {retry_e}")
                    import traceback
                    traceback.print_exc()
        else:
            print("Warning: Attempted to send audio but stream_sid is not set")

    async def send_clear_message_to_twilio(self):
        if self.stream_sid:
            try:
                clear_message = {"event": "clear", "streamSid": self.stream_sid}
                if self.websocket.application_state == WebSocketState.CONNECTED:
                    await self.websocket.send_text(json.dumps(clear_message))
                    print("Sent clear message to Twilio")
                else:
                    print(f"WebSocket not connected, state: {self.websocket.application_state}")
            except WebSocketDisconnect as e:
                print(f"WebSocket disconnected while sending clear message: {e}")
            except RuntimeError as e:
                print(f"Runtime error while sending clear message: {e}")
            except Exception as e:
                print(f"Unexpected error sending clear message: {type(e).__name__}: {e}")
                print("Attempting retry for clear message send...")
                try:
                    if self.websocket.application_state == WebSocketState.CONNECTED:
                        await self.websocket.send_text(json.dumps(clear_message))
                        print("Retry successful - Sent clear message to Twilio")
                    else:
                        print(f"Retry failed - WebSocket still not connected, state: {self.websocket.application_state}")
                except Exception as retry_e:
                    print(f"Retry failed for clear message send: {type(retry_e).__name__}: {retry_e}")
                    import traceback
                    traceback.print_exc()
        else:
            print("Warning: Attempted to send clear message but stream_sid is not set")

    async def handle_twilio_message(self, data):
        try:
            event_type = data.get("event")
            print(f"Handling Twilio message - Event type: {event_type}")
            
            if event_type == "start":
                self.stream_sid = data["start"]["streamSid"]
                print(f"Stream started with SID: {self.stream_sid}")
            elif event_type == "media" and self.input_callback:
                audio_data = base64.b64decode(data["media"]["payload"])
                print(f"Received audio data: {len(audio_data)} bytes")
                self.input_callback(audio_data)
            elif event_type == "media" and not self.input_callback:
                print("Warning: Received media event but no input callback is set")
            else:
                print(f"Unhandled event type: {event_type}")
        except KeyError as e:
            print(f"Missing key in Twilio message data: {e}")
            print(f"Available keys: {list(data.keys())}")
            print(f"Full message data: {data}")
        except Exception as e:
            print(f"Error in handle_twilio_message: {type(e).__name__}: {e}")
            print(f"Message data: {data}")
            print("Attempting retry in handle_twilio_message...")
            try:
                # Retry the same operation
                event_type = data.get("event")
                if event_type == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    print(f"Retry successful - Stream started with SID: {self.stream_sid}")
                elif event_type == "media" and self.input_callback:
                    audio_data = base64.b64decode(data["media"]["payload"])
                    print(f"Retry successful - Received audio data: {len(audio_data)} bytes")
                    self.input_callback(audio_data)
                else:
                    print(f"Retry successful - Handled event type: {event_type}")
            except Exception as retry_e:
                print(f"Retry failed in handle_twilio_message: {type(retry_e).__name__}: {retry_e}")
                import traceback
                traceback.print_exc()
