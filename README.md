# 🌲 Trail Condition Predictor & Dashboard

An automated, data-driven Python system that fetches historical and forecast weather data for seven major mountain biking regions around Vancouver and Squamish, evaluates trail conditions using a sophisticated drainage-aware soil moisture decay model (or Gemini LLM analysis), and publishes a beautiful condition briefing to a GitHub Pages dashboard.

## Features

- **Decoupled Architecture**: All regions, coordinates, condition thresholds, and weather heuristics are externalized in `config/config.yaml`.
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
  - **Forecast Overrides**: Prevents dry trails from rating well if active rainfall during the ride immediately saturates the dirt.
- **Dual-Mode Condition Evaluation**:
  - **LLM Mode (Gemini)**: If `GEMINI_API_KEY` is present, weather history, forecasts, and drainage indexes are evaluated by Gemini to determine conditions and auto-generate highly engaging verbal reasonings.
  - **Rule Mode (Fallback)**: If no key is set or the API fails, a deterministic Python decay model computes the conditions and generates a highly descriptive templated analysis.
- **Beautiful HTML Conditions Dashboard**:
  - Responsive web layout hosted for free on GitHub Pages.
  - High-contrast color-coded condition badges (`dusty`, `dry`, `good`, `damp`, `wet`, `muddy`).
  - Regional cards displaying summaries of the past 7 days of weather alongside full 2-hour resolution forecast grids for all 3 forecast days.
  - Automated trail warnings for regions showing muddy status or facing heavy rainfall (>10mm).
- **Automated Deployments**: Run on a cron schedule every 3 hours during active waking hours via GitHub Actions, auto-publishing to your Pages site.

---

## Local Setup

### 1. Prerequisites
Ensure you have Python 3.8+ installed.

### 2. Install Dependencies
Clone the repository and install required packages:
```bash
pip install -r requirements.txt
```

### 3. Running Locally
Run the orchestrator script to fetch weather, evaluate conditions, and write the output dashboard:
```bash
python3 main.py
```
This writes the generated dashboard directly to `output/index.html`. You can open this file in your browser to preview the visual aesthetics, table layouts, and styling.

- To run with fallback rules instead of calling the Gemini API:
  ```bash
  python3 main.py --no-gemini
  ```
- To run with the cheaper dry-run Gemini model (e.g., for testing):
  ```bash
  python3 main.py --dry-run
  ```

### 4. Local Secrets
To run Gemini locally without setting environment variables on every terminal session:
1. Copy `config/secrets.yaml.template` to create a `config/secrets.yaml` file:
   ```bash
   cp config/secrets.yaml.template config/secrets.yaml
   ```
2. Open `config/secrets.yaml` and enter your Gemini API Key:
   ```yaml
   GEMINI_API_KEY: "your_copied_api_key_here"
   ```
   *(Note: `config/secrets.yaml` is automatically ignored in `.gitignore` so your key will never be pushed to Git).*

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

---

## GitHub Actions & Pages Deployment Guide

The dashboard is configured to update on schedule every 3 hours from 4:00 AM to 10:00 PM Vancouver Time (UTC cron: `0 2,5,11,14,17,20,23 * * *`).

### Setup Steps:
1. **Enable GitHub Pages**:
   - Go to your GitHub repository -> **Settings** -> **Pages**.
   - Under **Build and deployment > Source**, select **GitHub Actions** from the dropdown menu.
2. **Add Gemini API Key Secret**:
   - Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions**.
   - Click **New repository secret** and add:
     - Name: `GEMINI_API_KEY`
     - Value: Your Google Gemini API Key. (If omitted, the Actions runner will automatically fall back to the deterministic local decay engine).
3. **Run Manually**:
   - Go to the **Actions** tab of your repository.
   - Select the **Deploy Trail Conditions Dashboard to Pages** workflow.
   - Click **Run workflow** to trigger a manual deployment. Once complete, your dashboard will be available at your GitHub Pages URL (`https://<username>.github.io/<repository-name>/`).
