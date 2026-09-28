import os
from dotenv import load_dotenv
import requests
from datetime import date
from meshtastic.tcp_interface import TCPInterface
import socket  
import time  
import logging

# Configure structured logging matching eqevents.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("nasaalert")

# Load environment variables from .env file
load_dotenv()

MESHTASTIC_IP = os.getenv("MESHTASTIC_IP", "192.168.50.46")
MESHTASTIC_CHANNEL = int(os.getenv("MESHTASTIC_CHANNEL", "0"))
NASA_API_KEY = os.getenv("NASA_API_KEY")

STATE_FILE = os.getenv("STATE_FILE", "data/last_alerted_neo.txt")
MAX_CHARS = 200

# Default template (<200 chars, includes emojis, miles, and JPL details link)
DEFAULT_TEMPLATE = "🔭 NASA NEO Watch: 🔭\n🌠 {name}\n🕰️ {approach_date_full}\n🛸 {formatted_distance} mi from 🌍\n🔗 [https://nasa.gov]({url})"

# --- RESILIENT TCP INTERFACE SUBCLASS ---
class ResilientTCPInterface(TCPInterface):
    """Keep the library heartbeat thread alive after a reconnectable write error."""

    def _writeBytes(self, payload: bytes) -> None:
        try:
            super()._writeBytes(payload)
        except (BrokenPipeError, OSError) as exc:
            if getattr(self, "_wantExit", False):
                raise
            logger.warning("Meshtastic TCP connection broke during write; reconnecting: %s", exc)
            reconnect = getattr(self, "_reconnect", None)
            if not callable(reconnect):
                raise
            reconnect()
# ----------------------------------------

def reset_state_file():
    """Clears the saved NEO alert history."""
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
            logger.info(f"🗑️ State file reset successfully: {STATE_FILE}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to reset state file: {e}")
            return False
    else:
        logger.info("ℹ️ No state file found to reset.")
        return True

def load_last_id():
    """Loads the neo_reference_id of the last object alerted from the state file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                last_id = f.read().strip()
                if last_id:
                    logger.info(f"✅ Memory loaded: Last alerted object ID was {last_id}.")
                    return last_id
        except Exception as e:
            logger.warning(f"⚠️ Could not read state file. Starting fresh. Error: {e}")
            return None
    else:
        logger.info("ℹ️ Memory initialized: No alert history found. Proceeding to check for NEOs.")
        return None

def save_last_id(neo_reference_id):
    """Saves the neo_reference_id of the currently alerted object."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            f.write(neo_reference_id)
        logger.info(f"✅ Memory updated: Saved ID {neo_reference_id} as the latest alert.")
        return True
    except Exception as e:
        logger.error(f"❌ Could not write to state file {STATE_FILE}. Alert memory failed. ({e})")
        return False

def findClosestEncounter(jd):
    """
    Analyzes the list of NEOs (jd) and finds the index of the object with the 
    minimum miss distance (kilometers).
    """
    asteroids = []
    for i in range(len(jd)):
        try:
            distance = jd[i]['close_approach_data'][0]['miss_distance']['kilometers']
            asteroids.append(float(distance))
        except (KeyError, IndexError):
            continue
    
    if not asteroids:
        return -1
        
    return asteroids.index(min(asteroids))

def is_node_port_available(ip, port=4403, timeout=2):
    """
    Performs a brief check to see if the Meshtastic TCP port is accessible.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((ip, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

def format_neo_message(neo_data, template=None):
    """
    Formats the alert message for a given NEO dictionary object.
    """
    name = neo_data['name']
    neo_id = neo_data['neo_reference_id']
    
    # Custom JPL URL with view=VOP filter
    jpl_url = f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={neo_id}&view=VOP"
    
    approach_data = neo_data['close_approach_data'][0]
    approach_date_full = approach_data['close_approach_date_full']
    
    # Extract miles directly from NASA response
    miss_distance_miles = approach_data['miss_distance']['miles']
    formatted_distance = f"{float(miss_distance_miles):,.2f}"

    active_template = template if template else DEFAULT_TEMPLATE

    return active_template.format(
        name=name,
        approach_date_full=approach_date_full,
        miss_distance_miles=miss_distance_miles,
        formatted_distance=formatted_distance,
        url=jpl_url
    )

def send_message_to_mesh(message, max_retries=3, retry_delay=10):
    """
    Connects to the local meshtastic node via TCP, validates message length,
    transmits payload, and pauses to allow LoRa packet dispatch before closing.
    """
    # 1. Message Length Safeguard (from eqevents.py)
    if len(message) > MAX_CHARS:
        logger.warning(f"Message exceeds {MAX_CHARS} characters ({len(message)} chars). Truncating.")
        message = message[:MAX_CHARS]
    else:
        logger.info(f"Message length validation passed: {len(message)} characters.")

    port_available = False
    
    # 2. Retry loop for pre-flight port check
    for attempt in range(1, max_retries + 1):
        logger.info(f"🔍 Pre-flight check: Verifying port 4403 availability on {MESHTASTIC_IP} (Attempt {attempt}/{max_retries})...")
        
        if is_node_port_available(MESHTASTIC_IP, port=4403):
            port_available = True
            logger.info("✅ Port 4403 is free and responsive!")
            break
            
        if attempt < max_retries:
            logger.warning(f"⚠️ Port busy or timed out. Waiting {retry_delay} seconds before trying again...")
            time.sleep(retry_delay)

    if not port_available:
        logger.error("❌ Aborting transmission sequence: Meshtastic interface remained busy or unavailable.")
        return False

    # 3. Transmit payload
    logger.info(f"Connecting to Meshtastic node at TCP {MESHTASTIC_IP}...")
    interface = None
    try:
        interface = ResilientTCPInterface(hostname=MESHTASTIC_IP)
        
        # Cancel heartbeat timer to avoid BrokenPipe socket error during close
        if hasattr(interface, 'heartbeatTimer') and interface.heartbeatTimer:
            interface.heartbeatTimer.cancel()

        logger.info(f"Sending message on channel {MESHTASTIC_CHANNEL}...")
        interface.sendText(text=message, channelIndex=MESHTASTIC_CHANNEL)
        
        # Give the node time to process and broadcast over LoRa (from eqevents.py)
        logger.info("Waiting for transmission to complete...")
        time.sleep(5)

        logger.info("✅ Message successfully sent to Meshtastic Node!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Meshtastic transmission failed: {e}")
        return False
    finally:
        if interface:
            interface.close()

def nasa_alert_scheduler(custom_template=None):
    """
    Main function entry point. Fetches NEO data, compares it to memory, 
    formats the alert message, and attempts to transmit it.
    """
    # 1. SETUP & FETCH
    ad_today = date.today().strftime("%Y-%m-%d")
    url = f"https://api.nasa.gov/neo/rest/v1/feed?start_date={ad_today}&end_date={ad_today}&api_key={NASA_API_KEY}"
    
    logger.info(f"--- Running NEO Check for {ad_today} ---")

    try:
        response = requests.get(url, timeout=12)
        response.raise_for_status()  
        jsn = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ FATAL ERROR: Could not fetch data from NASA API. ({e})")
        return False

    # 2. DATA PROCESSING
    if "near_earth_objects" not in jsn:
        logger.error("❌ ERROR: No near-earth object data found for this date.")
        return False
  
    base = jsn['near_earth_objects'][ad_today]
    closest_index = findClosestEncounter(base)

    if closest_index == -1:
        logger.error("❌ ERROR: Failed to find valid NEO data.")
        return False
        
    closest_neo = base[closest_index]
    current_neo_id = closest_neo['neo_reference_id']

    # 3. MEMORY CHECK (DE-DUPLICATION)
    last_alerted_id = load_last_id()
    if last_alerted_id and last_alerted_id == current_neo_id:
        logger.info(f"😴 ALERT SKIPPED: The closest object ({current_neo_id}) was alerted previously today. No action taken.")
        return False  

    # 4. DATA EXTRACTION & FORMATTING
    try:
        message = format_neo_message(closest_neo, template=custom_template)
        logger.info(f"🚀 Formatted message payload:\n{message}")
        
        if send_message_to_mesh(message):
            save_last_id(current_neo_id)
            return True
        else:
            return False

    except Exception as e:
        logger.error(f"❌ An error occurred while formatting or sending the message: {e}")
        return False

if __name__ == "__main__":
    nasa_alert_scheduler()
