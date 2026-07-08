# Cellular Bridge (`cellular-bridge`)

A Dockerized microservice running on Raspberry Pi 5 to turn a SIM800L cellular HAT into a private RESTful SMS API gateway.

---

## Hardware Wiring & Configuration

Connecting the SIM800L directly to the Raspberry Pi 5's 5V or 3.3V pins is **strongly discouraged**. The SIM800L requires **3.4V to 4.4V** (ideally **4.0V - 4.2V**) and draws transient current spikes up to **2A** during network transmission. This will trigger brownouts or damage the Pi if powered directly.

You **must** use the **LM2596 DC-DC Buck Converter** to safely step down the voltage and provide sufficient current.

### 1. Power Setup (LM2596)
1. **Input Power**: Connect a DC power source (e.g., 5V to 12V external power supply, or the Pi's 5V Pin 2/4 *only* if using the official 5A Pi 5 power adapter) to the LM2596 `IN+` and `IN-` terminals.
2. **Calibration**: **Before connecting to the SIM800L**, power on the source and use a multimeter to measure the voltage across the LM2596 `OUT+` and `OUT-` terminals. Turn the brass screw potentiometer until the output reads **exactly 4.0V**.
3. **Output Power**: Connect `OUT+` to the SIM800L `VCC` pin, and `OUT-` to the SIM800L `GND` pin.

### 2. Pin Connections Table

| Component A | Component B | Connection Type / Details |
| :--- | :--- | :--- |
| **LM2596 OUT+** | **SIM800L VCC** | Power (regulated 4.0V) |
| **LM2596 OUT-** | **SIM800L GND** | Power Ground |
| **Raspberry Pi 5 GND (Pin 6)** | **SIM800L GND** | **Common Ground** (CRITICAL for serial comms) |
| **Raspberry Pi 5 TXD (GPIO 14, Pin 8)** | **SIM800L RXD** | Serial TX -> RX (3.3V logic tolerant) |
| **Raspberry Pi 5 RXD (GPIO 15, Pin 10)** | **SIM800L TXD** | Serial RX <- TX |

> [!WARNING]
> You must connect the **GND** from the Raspberry Pi 5, the **GND** of the SIM800L, and the **OUT-** of the LM2596 together (Common Ground). Without a shared reference ground, the serial signals will contain noise and fail to register.

---

### 3. Raspberry Pi 5 Serial Configuration

Before running the container, you must configure the Raspberry Pi's physical GPIO serial pins:

1. SSH into your Raspberry Pi 5.
2. Run the Raspberry Pi configuration utility:
   ```bash
   sudo raspi-config
   ```
3. Navigate to **Interface Options** -> **Serial Port**.
4. When prompted:
   - *Would you like a login shell to be accessible over serial?* -> Select **No** (frees up TX/RX pins).
   - *Would you like the serial port hardware to be enabled?* -> Select **Yes**.
5. Save, exit, and reboot your Raspberry Pi:
   ```bash
   sudo reboot
   ```
6. Verify the serial interface exists. It is usually mapped to:
   ```bash
   ls -la /dev/ttyAMA0
   ```

---

## Deployment (via Docker Compose)

1. Create a `.env` file in the root of the project to configure your API key:
   ```env
   CELLULAR_BRIDGE_API_KEY=your_secure_api_key_here
   ```

2. Start the API service inside the `cellular-bridge` directory:
   ```bash
   # Build and run the container in detached mode
   docker compose up --build -d
   ```

---

## API Documentation

The API runs on port `8080`.

### 1. Health Check
Verifies if the container can reach and communicate with the SIM800L HAT over the physical device mount. This endpoint is public and does not require authentication:
```http
GET http://[YOUR_PI_IP]:8080/health
```

#### Response (Success)
```json
{
  "status": "healthy",
  "hardware": "SIM800L connected"
}
```

---

### 2. Send SMS
Sends a text message to a specified mobile number. Use international phone formatting (e.g., `+639171234567`).

**Note:** If `CELLULAR_BRIDGE_API_KEY` is set in the environment, you must authenticate using the `X-API-Key` header.

```http
POST http://[YOUR_PI_IP]:8080/send-sms
Content-Type: application/json
X-API-Key: your_secure_api_key_here

{
  "phone_number": "+639171234567",
  "message": "Hello from your Raspberry Pi 5 Cellular Bridge SMS gateway!"
}
```

#### Response (Success)
```json
{
  "success": true,
  "phone_number": "+639171234567",
  "message": "Hello from your Raspberry Pi 5 Cellular Bridge SMS gateway!",
  "raw_response": "OK\r\n\r\n+CMGS: 42"
}
```
