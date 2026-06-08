# 🌲 Trail Condition Predictor & Email Briefing System

An automated, data-driven Python system that fetches historical and forecast weather data for seven major mountain biking regions around Vancouver and Squamish, evaluates trail conditions using a sophisticated drainage-aware soil moisture decay model (or Gemini LLM analysis), and emails a daily HTML briefing.

## Features

- **Decoupled Architecture**: All regions, coordinates, condition thresholds, and weather heuristics are externalized in `config.yaml`.
- **7 Mountain Biking Regions**:
  - Mount Fromme (North Vancouver)
  - Mount Seymour (North Vancouver)
  - Cypress Mountain (West Vancouver)
  - Burke Mountain (Coquitlam)
  - Eagle Mountain (Coquitlam)
  - Alice Lake (Squamish)
  - Diamond Head (Squamish)
- **Advanced Core Heuristics**:
  - Exponential decay model tracking the last 7 days of rainfall & snowmelt.
  - Drying efficiency adjustments based on daily max temperature and mean relative humidity.
  - **Forecast Rain Overrides**: Prevents dry trails from rating well if active rainfall during the ride immediately saturates the dirt.
- **Dual-Mode Condition Evaluation**:
  - **LLM Mode (Gemini)**: If `GEMINI_API_KEY` is present, weather history, forecasts, and drainage indexes are evaluated by Gemini 2.5 Flash to determine conditions and auto-generate highly engaging verbal reasonings.
  - **Rule Mode (Fallback)**: If no key is set or the API fails, a deterministic Python decay model computes the conditions and generates a highly descriptive templated analysis.
- **Beautiful HTML Email Briefing**:
  - Responsive layout compatible with modern desktop/mobile clients.
  - High-contrast color-coded condition badges (`dusty`, `dry`, `good`, `damp`, `wet`, `muddy`).
  - Regional cards linking coordinates directly to Google Maps, displaying summaries of the past 7 days of weather alongside a 4-day forecast table.
  - Automated trail warnings for regions showing muddy status or facing heavy rainfall (>10mm).
- **CI/CD Ready**: Configured to run every morning via GitHub Actions.

---

## Local Setup

### 1. Prerequisites
Ensure you have Python 3.8+ installed.

### 2. Install Dependencies
Clone the repository and install required packages:
```bash
pip install -r requirements.txt
```

### 3. Running Locally in Dry-Run Mode
The script has a `--dry-run` flag which allows you to fetch real weather data, compute all conditions, and export the rendered HTML email output without setting up SMTP credentials:
```bash
python main.py --dry-run
```
This generates an `email_preview.html` file in the project folder. Double-click it to inspect the visual aesthetics, table layouts, and styling in your browser.

### 4. Running Locally with Email Sending
To send the email, set up the SMTP environment variables and run without `--dry-run`:
```bash
# On Windows (PowerShell):
$env:SMTP_SERVER="smtp.gmail.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your-email@gmail.com"
$env:SMTP_PASSWORD="your-app-password"
$env:RECIPIENT_EMAILS="recipient1@gmail.com,recipient2@gmail.com"
$env:GEMINI_API_KEY="your-gemini-key-optional"
python3 main.py

# On Linux/macOS:
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="your-email@gmail.com"
export SMTP_PASSWORD="your-app-password"
export RECIPIENT_EMAILS="recipient1@gmail.com,recipient2@gmail.com"
export GEMINI_API_KEY="your-gemini-key-optional"
python3 main.py
```

### 5. Alternative: Using a local `secrets.yaml` configuration file
To avoid setting environment variables on every terminal session:
1. Copy `secrets.yaml.template` to create a `secrets.yaml` file in the project root:
   ```bash
   cp secrets.yaml.template secrets.yaml
   ```
2. Open `secrets.yaml` and enter your credentials:
   ```yaml
   GEMINI_API_KEY: "your_copied_api_key_here"
   SMTP_SERVER: "smtp.gmail.com"
   SMTP_PORT: 587
   SMTP_USER: "your-email@gmail.com"
   SMTP_PASSWORD: "your-app-password"
   RECIPIENT_EMAILS: "recipient1@gmail.com,recipient2@gmail.com"
   ```
3. Run the script. The credentials will be loaded automatically:
   ```bash
   python3 main.py --dry-run
   ```
   *(Note: `secrets.yaml` is automatically listed in `.gitignore` so your keys will never be pushed to Git).*

---

## Heuristics & Rules Engine

The local rule engine computes a **Soil Saturation Score** for each forecasting day $t$:
$$S_t = \sum_{i=1}^{7} (\text{Rain}_{t-i} + \text{Snow}_{t-i} \times 2.0) \times \lambda^i$$
where:
- $\lambda$ is the `decay_factor` (`0.6` by default), representing soil water runoff and evaporation.
- $2.0 \times \text{Snow}$ accounts for the delayed melting moisture holding capacity.

The base condition score combines the history score and forecast rain, scaled by the region's unique **Drainage Index** ($D$):
$$\text{Score}_t = (S_t \times W_{\text{past}} + \text{Forecast Rain}_t \times W_{\text{forecast}}) \times D$$

### Regional Drainage Properties
- **Alice Lake** ($D=0.6$) / **Diamond Head** ($D=0.8$): Fast draining granite slabs and sandy glades. Slower to turn muddy, dries rapidly.
- **Fromme** ($D=1.0$) / **Seymour** ($D=1.0$) / **Cypress** ($D=0.8$): Standard Shore dirt. Drains moderately, holds dampness under deep tree canopy.
- **Burke Mountain** ($D=1.4$) / **Eagle Mountain** ($D=1.4$): Slow draining loam and clay. Extremely vulnerable to puddle saturation.

### Weather Drying Adjustments
The score is adjusted up or down based on daily drying conditions:
- **Warm Temp** ($\ge 20^\circ\text{C}$): Score is multiplied by `0.7` (dries faster).
- **Cold Temp** ($< 8^\circ\text{C}$): Score is multiplied by `1.3` (dries slower).
- **High Humidity** ($\ge 85\%$): Score is multiplied by `1.2` (dries slower).
- **Low Humidity** ($< 50\%$): Score is multiplied by `0.8` (dries faster).

### Active Forecast Overrides
Regardless of preceding week dryness, active forecast rain on the ride day overrides the score:
- **$\ge 12.0$ mm**: Immediately downgraded to `muddy`.
- **$\ge 5.0$ mm**: Upgraded to at least `wet`.
- **$\ge 1.5$ mm**: Upgraded to at least `damp`.

---

## GitHub Actions Deployment Guide

The briefing system is configured to run daily at 6:00 AM PST (7:00 AM PDT) using GitHub Actions.

### Setup Steps:
1. **Push code to GitHub**: Create a repository and push this project's files.
2. **Add Repository Secrets**:
   - Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions**.
   - Click **New repository secret** for each of the following:
     - `SMTP_SERVER`: The host address of your SMTP server (e.g., `smtp.gmail.com` or `smtp.sendgrid.net`).
     - `SMTP_PORT`: Port number (e.g., `587` for STARTTLS or `465` for SSL).
     - `SMTP_USER`: Your email address or username used to send the emails.
     - `SMTP_PASSWORD`: Your password or app-specific password (strongly recommended for Gmail).
     - `RECIPIENT_EMAILS`: Comma-separated list of email addresses to receive the briefing.
     - `GEMINI_API_KEY`: *(Optional)* Your Google GenAI API Key. If omitted, the system automatically runs the rule-based local decay engine.
3. **Run Manually**:
   - Go to the **Actions** tab of your repository.
   - Click on the **Daily Trail Conditions Report** workflow.
   - Click the **Run workflow** dropdown and select **Run workflow**. This immediately triggers a briefing send!
