# ☄️ Asteroid Alert System 🔭
## 🚀 Overview

**Asteroid Alert System** is a Python-based monitoring system that tracks NASA's Near-Earth Object (NEO) data for approaching asteroids and broadcasts scheduled alerts over a Meshtastic LoRa mesh network via TCP.

When a significant object is detected, the system generates a concise alert—complete with approach trajectory links, flight distance, and time—and broadcasts it directly across a local **Meshtastic LoRa** mesh network via TCP.

## ✨ Features

*   **NASA API Integration:** Fetches daily NEO data from NASA's JPL (Asteroids - NeoWs) daily feed.  
Example api query  (https://api.nasa.gov/neo/rest/v1/neo/3542519?api_key=DEMO_KEY)
*   **NASA SBDB Lookup:** The url generated for the event leverages Nasa's Small-Body Database Lookup to display object details.
*   **NASA SBDB Orbit Viewer:** url filter parameter included to SBDB Orbit Viewer to playback and review object's orbit trajectory relevant to time by default.
*   **De-duplication:** Saves the `neo_reference_id` of the last alerted object to a state file (`/last_alerted_neo.txt`) to prevent spamming alerts for the same object on subsequent runs.
*   **Meshtastic Broadcast:** Connects to a local Meshtastic node via TCP and transmits the formatted alert message over the configured LoRa channel.
*   **Resilient Connection:** Includes logic to handle transient network issues when connecting to the Meshtastic node.
*   **Message Formatting:** Generates a clean, concise message adhering to a specified character limit, including crucial details like name, approach date, and formatted distance.

## ⚙️ Setup

### Prerequisites

Ensure you have Python 3.6+ installed.

### Installation

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables:**
    Create a `.env` file in the root directory and populate it with your credentials:
    ```ini
    # .env file
    MESHTASTIC_IP=192.168.0.1
    MESHTASTIC_CHANNEL=0
    NASA_API_KEY=YOUR_NASA_API_KEY_HERE
    STATE_FILE=/last_alerted_neo.txt
    ```

3.  **Meshtastic Node:**
    Ensure your Meshtastic radio is powered on, configured, and accessible at the IP address specified in `.env`.

## ▶️ Usage

Run the main script:
```bash
python asteroidalert/nasaalert.py
```

The script will check for today's NEOs, compare them against the last known alert, and broadcast if necessary.

## 🛠️ Customization

**Example Output Message:**

🔭 NASA NEO Watch: 🔭  
🌠 523934 (1998 FF14)  
🕰️ 2026-Sep-28 13:19  
🛸 9,565,077.94 mi from 🌍  
🔗 [https://nasa.gov](https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr=2523934&view=VOP)  

You can customize the alert message template in `nasaalert.py` within the `DEFAULT_TEMPLATE` variable for different output formats.

**Example Orbit Viewer:**  *(can follow orbit of object and playback relevant to time.)*  
<img style=left width="20%" height="20%" alt="orbit-viewer-snapshot" src="https://github.com/user-attachments/assets/d8283bbb-392b-45af-a0d9-8a14928bca32" />
