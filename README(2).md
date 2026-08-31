# PCA Energy Analysis with marimo

This repository contains interactive **marimo** applications for exploratory energy analysis using utility data, weather normalization, and Principal Component Analysis (PCA).

The notebooks are designed for facilities and energy-management workflows where utility data are available but detailed BAS or equipment-level data may be limited.

## Applications

### `erau_chiller_utility_weather_pca_marimo.py`

Central chiller plant utility and weather-normalized performance analysis.

The app:

- Loads monthly or billing-period electricity data for multiple plant meters
- Maps meter streams into North and South central plant totals
- Retrieves hourly historical weather from Open-Meteo
- Calculates cooling degree days, humidity, dew point, estimated wet-bulb temperature, and hot/humid-hour metrics
- Builds weather-normalized electricity baselines
- Calculates actual-versus-expected energy use
- Calculates a plant-level Performance Index
- Flags unusually high- and low-use billing periods
- Calculates individual meter contributions using complete billing periods only
- Uses PCA to identify similar weather regimes and compare energy performance under comparable conditions
- Estimates the financial magnitude of above-baseline consumption for screening purposes
- Exports analysis results to Excel
- Generates a Word management report

> This is a utility- and weather-based screening analysis. It does **not** calculate actual chiller kW/ton because cooling production and plant-level operational data are not currently included.

---

### `fpl_weather_pca_marimo_debugged.py`

Interactive PCA and weather analysis for FPL electricity data.

Use this app to explore relationships between electricity consumption and weather variables and to identify patterns, clusters, and unusual observations in utility data.

---

### `prescott_building_only_pca_marimo.py`

Building-level PCA analysis for Prescott utility-meter data.

This app is intended to explore relationships across building electricity consumption and identify common patterns, outliers, and groups of buildings with similar energy behavior.

---

# Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer recommended
- Internet access for historical weather retrieval where applicable

The primary Python packages used by the applications are:

```text
marimo
pandas
numpy
matplotlib
scikit-learn
openpyxl
requests
python-docx
```

## Install Python packages

From Command Prompt or Terminal:

```bash
python -m pip install --user marimo pandas numpy matplotlib scikit-learn openpyxl requests python-docx
```

If `python` is not recognized, confirm that Python is installed and available on your PATH.

---

# Clone the repository

Using Git:

```bash
git clone https://github.com/kmetz-erau/PCA.git
cd PCA
```

To update an existing local copy after changes are pushed to GitHub:

```bash
git pull
```

Repository:

https://github.com/kmetz-erau/PCA

---

# Run the marimo apps

## Chiller plant analysis

```bash
python -m marimo run erau_chiller_utility_weather_pca_marimo.py
```

To open the notebook in the marimo editor:

```bash
python -m marimo edit erau_chiller_utility_weather_pca_marimo.py
```

## FPL weather PCA

```bash
python -m marimo run fpl_weather_pca_marimo_debugged.py
```

## Prescott building PCA

```bash
python -m marimo run prescott_building_only_pca_marimo.py
```

Before running an app, you can check it for marimo notebook issues with:

```bash
python -m marimo check erau_chiller_utility_weather_pca_marimo.py
```

---

# Chiller Plant Input Data

The central chiller plant app expects a CSV or Excel file containing at least:

| Column | Description |
|---|---|
| `meter_name` | Utility meter or service description |
| `start_date` | Billing-period start date |
| `end_date` | Billing-period end date |
| `kwh` | Electricity consumption for the period |

A `cost` column may also be included.

Example:

```text
meter_name,start_date,end_date,kwh,cost
NORTH TES CAMPUS PART 1,2026-01-01,2026-01-31,411360,42150.00
```

Exact utility billing dates are preferred. Calendar-month dates can be used when exact read dates are unavailable.

## Meter grouping

The chiller app groups utility meters into two plant totals:

**North Plant**

- North Part 1
- North Part 2
- North Part 3

**South Plant**

- South TES 1
- South TES 2

Missing kWh values remain missing and are not automatically converted to zero.

---

# Methodology

## Weather normalization

Historical hourly weather is retrieved and aggregated to each utility billing period.

Weather variables include:

- Mean, maximum, and minimum dry-bulb temperature
- Relative humidity
- Dew point
- Estimated wet-bulb temperature
- Cooling Degree Days using a 65 F base
- Humid cooling hours
- Hours above 80 F
- Hours above 90 F

A plant-level regression estimates expected electricity consumption from weather and billing-period conditions.

The difference between actual and expected energy is the **residual**:

```text
Residual kWh = Actual kWh - Expected kWh
```

The **Performance Index** is:

```text
Performance Index = Actual kWh / Expected kWh
```

Interpretation:

- `1.00` = actual consumption matched model expectation
- `1.10` = approximately 10% above expectation
- `0.90` = approximately 10% below expectation

## Model diagnostics

The analysis reports metrics such as:

- **R-squared (R2):** how much of the variation in electricity consumption is explained by the model
- **MAPE:** the average absolute percentage difference between predicted and actual consumption

These should be interpreted together. Large MAPE values can be distorted by periods with very small actual consumption.

---

# Principal Component Analysis

PCA is used as a **diagnostic tool**, not as a replacement for the weather-normalized energy model.

Weather variables are highly correlated. For example, high-temperature months also tend to have higher cooling degree days, more hot hours, and higher wet-bulb conditions.

PCA compresses these correlated weather variables into a smaller set of independent components representing broader **weather regimes**.

This enables a useful facilities question:

> If two billing periods experienced similar combinations of weather conditions, why did the plant use substantially more electricity in one period than the other?

Periods located close together in PCA space experienced broadly similar weather. Large differences in energy residuals between nearby points may indicate that weather alone does not explain the difference and that plant operations should be reviewed.

Potential operational factors include:

- Chiller staging
- Chilled-water setpoints
- Pump operation
- Cooling-tower operation
- Thermal energy storage strategy
- Equipment outages
- Control overrides
- Maintenance events
- Changes in connected cooling load
- Metering or data-quality issues

---

# Meter Contribution Analysis

Meter contribution percentages are calculated only for billing periods where all expected meters for a plant contain valid kWh data.

This prevents missing meter readings from artificially increasing the apparent contribution of the remaining meters.

Contribution percentages therefore sum to 100% within each plant for the periods used in this analysis.

---

# Outputs

Depending on the app and available data, outputs can include:

- Interactive tables
- Electricity-consumption trend charts
- Weather-normalized actual-versus-expected charts
- Performance Index trends
- PCA scores and loading tables
- PCA weather-regime charts
- Flagged high- and low-use periods
- Meter contribution summaries
- Model diagnostics
- Excel analysis workbook
- Word management report

---

# Important Limitations

Utility-level analysis can identify **when** plant electricity consumption appears unusual, but it cannot by itself determine **why**.

The current chiller workflow does not directly calculate:

- Actual cooling tons
- Actual plant kW/ton
- Individual chiller efficiency
- Chiller staging efficiency
- Pump efficiency
- Cooling-tower efficiency
- Thermal energy storage efficiency

These require additional plant or BAS data.

## Recommended BAS data for future analysis

The analysis becomes considerably more robust with 15-minute or hourly BAS trends such as:

- Total plant kW
- Chilled-water supply temperature
- Chilled-water return temperature
- Chilled-water flow (GPM)
- Individual chiller run status
- Chiller loading
- Individual chiller kW, when available
- Chilled-water pump status and VFD speed
- Condenser-water pump status and VFD speed
- Cooling-tower fan status and VFD speed
- Condenser-water supply and return temperatures
- Chilled-water differential pressure
- Thermal energy storage charge/discharge status

With flow, temperature differential, and electrical demand, actual plant efficiency can be calculated:

```text
Cooling Tons ~= GPM x Delta-T / 24

Plant kW/ton = Plant kW / Cooling Tons
```

This allows the workflow to progress from utility-level screening to true plant-performance diagnostics.

---

# Suggested Analytics Progression

A practical progression for facilities energy analytics is:

```text
Utility Data
    -> Weather Normalization
    -> Residual / Anomaly Analysis
    -> PCA Weather-Regime Analysis
    -> Operational Investigation
    -> BAS Integration
    -> Actual Plant kW/ton Analysis
```

The intent is not to replace plant engineering judgment, but to use data analytics to identify where engineering attention is most valuable.

---

# Data Quality

Before interpreting anomalies as equipment or controls problems, validate:

- Missing meter readings
- Near-zero consumption periods
- Duplicate billing records
- Meter replacements
- Account changes
- Plant-service changes
- Incomplete billing periods
- Changes in connected load

Data-quality anomalies should be separated from genuine operational-performance anomalies wherever possible.

---

# Updating Your Local Copy

After changes are added to GitHub:

```bash
cd C:\Users\YOUR_USERNAME\PCA
git pull
```

Then run the desired app again:

```bash
python -m marimo run erau_chiller_utility_weather_pca_marimo.py
```

---

# Disclaimer

These applications are intended for exploratory facilities-energy analysis and operational screening. Statistical results, anomaly flags, PCA results, and estimated above-baseline costs should not be interpreted as guaranteed energy savings or measured equipment efficiency without additional engineering validation.
