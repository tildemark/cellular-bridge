import time
import logging
import serial
import os
from fastapi import FastAPI, HTTPException, Security, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sms-sender")

tags_metadata = [
    {
        "name": "SMS Operations",
        "description": "Send SMS messages using the cellular transceiver.",
    },
    {
        "name": "Admin Key Management",
        "description": "Generate, list, and revoke API keys for client application access. Requires Admin Key.",
    },
    {
        "name": "System",
        "description": "System health and status endpoints.",
    },
]

app = FastAPI(
    title="SMS Sender API",
    description="Raspberry Pi 5 + SIM800L cellular gateway for sending and receiving SMS via HTTP REST",
    version="1.0.0",
    openapi_tags=tags_metadata
)

import json
import secrets

# API Key configuration
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key for clients or Master Admin Key")
SMS_SENDER_API_KEY = os.getenv("SMS_SENDER_API_KEY")

KEYS_FILE = "data/api_keys.json"

def load_keys():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading keys file: {e}")
        return {}

def save_keys(keys_data):
    if not os.path.exists("data"):
        os.makedirs("data")
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(keys_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving keys file: {e}")

def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if SMS_SENDER_API_KEY:
        if api_key == SMS_SENDER_API_KEY:
            return api_key
        keys_data = load_keys()
        if api_key in keys_data.values():
            return api_key
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API Key"
        )
    return api_key

def verify_admin_key(api_key: str = Security(API_KEY_HEADER)):
    if SMS_SENDER_API_KEY:
        if api_key != SMS_SENDER_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Master Admin API Key is required for this operation"
            )
    return api_key

class KeyCreateRequest(BaseModel):
    app_name: str

class KeyCreateResponse(BaseModel):
    app_name: str
    key: str

class RevokeResponse(BaseModel):
    success: bool
    message: str

class HealthResponse(BaseModel):
    status: str
    hardware: str | None = None
    error: str | None = None

class SMSSuccessResponse(BaseModel):
    success: bool
    phone_number: str
    message: str
    raw_response: str

SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = 9600

class SMSRequest(BaseModel):
    phone_number: str
    message: str

def send_at_command(ser, cmd, expected_response="OK", delay=0.5, timeout=5):
    ser.write((cmd + "\r\n").encode())
    time.sleep(delay)
    response = ser.read_all().decode(errors="ignore")
    logger.info(f"Command: {cmd} -> Response: {response.strip()}")
    if expected_response in response:
        return response
    return None

def get_serial_device(port=SERIAL_PORT, baud=BAUD_RATE, timeout=10):
    ser = serial.Serial(port, baud, timeout=timeout)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    # Send ESC to cancel any active SMS input prompt
    ser.write(b'\x1b')
    time.sleep(0.2)
    ser.read_all()
    # Disable local echo to prevent command loops/responses in output
    send_at_command(ser, "ATE0", delay=0.2)
    return ser


@app.get(
    "/api/keys",
    response_model=dict[str, str],
    tags=["Admin Key Management"],
    summary="List all registered API keys",
    description="Retrieves a list of all client application names and their associated API keys. Requires the Master Admin Key."
)
def get_api_keys(admin_key: str = Depends(verify_admin_key)):
    return load_keys()

@app.post(
    "/api/keys",
    response_model=KeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin Key Management"],
    summary="Create a new client API key",
    description="Generates a new API key for the specified application name. Requires the Master Admin Key."
)
def create_api_key(payload: KeyCreateRequest, admin_key: str = Depends(verify_admin_key)):
    app_name = payload.app_name.strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="Application name cannot be empty")
    keys_data = load_keys()
    if app_name in keys_data:
        raise HTTPException(status_code=400, detail="Key already exists for this application")
    new_key = secrets.token_hex(16)
    keys_data[app_name] = new_key
    save_keys(keys_data)
    return {"app_name": app_name, "key": new_key}

@app.delete(
    "/api/keys/{app_name}",
    response_model=RevokeResponse,
    tags=["Admin Key Management"],
    summary="Revoke an existing API key",
    description="Deletes the API key associated with the specified application name. Requires the Master Admin Key."
)
def delete_api_key(app_name: str, admin_key: str = Depends(verify_admin_key)):
    keys_data = load_keys()
    if app_name not in keys_data:
        raise HTTPException(status_code=404, detail="Key not found for this application")
    del keys_data[app_name]
    save_keys(keys_data)
    return {"success": True, "message": f"Key for {app_name} revoked successfully"}

@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False
)
def get_dashboard():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h3>Error loading dashboard: {str(e)}</h3>", status_code=500)

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Service health check",
    description="Verifies container health and checks physical serial communication with the SIM800L module."
)
def health_check():
    try:
        ser = get_serial_device(timeout=3)
        res = send_at_command(ser, "AT")
        ser.close()
        if res:
            return {"status": "healthy", "hardware": "SIM800L connected"}
        return {"status": "unhealthy", "error": "SIM800L did not respond to AT"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post(
    "/send-sms",
    response_model=SMSSuccessResponse,
    tags=["SMS Operations"],
    summary="Send an SMS message",
    description="Instructs the SIM800L module to transmit a text message to the specified phone number. Requires a valid API Key or Master Admin Key."
)
def send_sms(payload: SMSRequest, api_key: str = Depends(verify_api_key)):
    logger.info(f"Received request to send SMS to {payload.phone_number}")
    try:
        ser = get_serial_device(timeout=10)
        
        # Test communication
        if not send_at_command(ser, "AT"):
            ser.close()
            raise HTTPException(status_code=502, detail="SIM800L hardware not responding")
            
        # Select Text Mode
        if not send_at_command(ser, "AT+CMGF=1"):
            ser.close()
            raise HTTPException(status_code=502, detail="Failed to set GSM text mode")
            
        # Set character set to GSM
        send_at_command(ser, 'AT+CSCS="GSM"')
            
        # Send recipient number
        ser.write(f'AT+CMGS="{payload.phone_number}"\r\n'.encode())
        time.sleep(0.5)
        
        # Write SMS body and terminate with Ctrl+Z (ASCII 26)
        ser.write((payload.message + chr(26)).encode())
        logger.info("Transmitting message payload...")
        
        # Wait for carrier response (can take several seconds)
        time.sleep(4)
        response = ser.read_all().decode(errors="ignore")
        ser.close()
        
        logger.info(f"Carrier Response: {response.strip()}")
        
        if "+CMGS:" in response:
            return {
                "success": True,
                "phone_number": payload.phone_number,
                "message": payload.message,
                "raw_response": response.strip()
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"SMS rejected by network carrier: {response.strip()}"
            )
            
    except Exception as e:
        logger.error(f"Error executing SMS dispatch: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
