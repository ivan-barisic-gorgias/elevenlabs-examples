import os
import json
import traceback
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from elevenlabs import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from twilio_audio_interface import TwilioAudioInterface
from starlette.websockets import WebSocketDisconnect
from function_handlers import handle_function_call

load_dotenv()

ELEVEN_LABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Twilio-ElevenLabs Integration Server"}


@app.post("/tools/{tool_name}")
async def handle_tool_call(tool_name: str, request: Request):
    """
    Handle tool/function calls from ElevenLabs agent.
    Tool name is provided as a path parameter, arguments in request body.
    """
    try:
        # Get arguments from request body
        request_body = await request.json()

        print(f"[ELEVENLABS TOOL] Received tool call: {tool_name}")
        print(f"[ELEVENLABS TOOL] Request headers: {dict(request.headers)}")
        print(f"[ELEVENLABS TOOL] Request body: {request_body}")
        print(f"[ELEVENLABS TOOL] Parameters extracted:")
        for key, value in request_body.items():
            print(f"[ELEVENLABS TOOL]   {key}: {value}")

        # Handle the function call
        result, error = handle_function_call(tool_name, request_body)

        if result is not None:
            print(f"[ELEVENLABS TOOL] Success - Tool {tool_name} returned: {result}")
            return result
        else:
            print(f"[ELEVENLABS TOOL] Error - Tool {tool_name} failed: {error}")
            return {"success": False, "error": error}

    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in request body: {e}"
        print(f"[ELEVENLABS TOOL] JSON Error for {tool_name}: {error_msg}")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error in tool endpoint: {e}"
        print(f"[ELEVENLABS TOOL] Exception for {tool_name}: {error_msg}")
        traceback.print_exc()
        return {"success": False, "error": error_msg}


@app.post("/twilio/inbound_call")
async def handle_incoming_call(request: Request):
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "Unknown")
    from_number = form_data.get("From", "Unknown")
    print(f"Incoming call: CallSid={call_sid}, From={from_number}")

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{request.url.hostname}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connection opened")

    audio_interface = TwilioAudioInterface(websocket)
    eleven_labs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    try:
        conversation = Conversation(
            client=eleven_labs_client,
            agent_id=ELEVEN_LABS_AGENT_ID,
            requires_auth=True, # Security > Enable authentication
            audio_interface=audio_interface,
            callback_agent_response=lambda text: print(f"Agent: {text}"),
            callback_user_transcript=lambda text: print(f"User: {text}"),
        )

        conversation.start_session()
        print("Conversation started")

        async for message in websocket.iter_text():
            if not message:
                continue
            try:
                await audio_interface.handle_twilio_message(json.loads(message))
            except Exception as e:
                print(f"Error handling Twilio message: {type(e).__name__}: {e}")
                print(f"Message content: {message}")
                print("Attempting retry...")
                try:
                    await audio_interface.handle_twilio_message(json.loads(message))
                    print("Retry successful")
                except Exception as retry_e:
                    print(f"Retry failed: {type(retry_e).__name__}: {retry_e}")
                    traceback.print_exc()

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception:
        print("Error occurred in WebSocket handler:")
        traceback.print_exc()
    finally:
        try:
            conversation.end_session()
            conversation.wait_for_session_end()
            print("Conversation ended")
        except Exception:
            print("Error ending conversation session:")
            traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
