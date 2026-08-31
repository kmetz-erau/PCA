import marimo

__generated_with = "0.17.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import io
    import numpy as np
    import pandas as pd
    import requests
    import matplotlib.pyplot as plt
    import marimo as mo

    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score, silhouette_score
    from sklearn.preprocessing import StandardScaler

    return (
        KMeans,
        LinearRegression,
        PCA,
        StandardScaler,
        io,
        mo,
        np,
        pd,
        plt,
        r2_score,
        requests,
        silhouette_score,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        # ERAU FPL Weather + GSF + PCA Analysis

        This notebook:

        1. Loads the enriched FPL billing workbook.
        2. Adds building GSF and chilled-water status.
        3. Downloads hourly Daytona Beach weather from Open-Meteo.
        4. Aggregates weather to each exact FPL billing period.
        5. Calculates CDD65, HDD65, temperature, humidity, dew point, wet bulb, and hot-hour metrics.
        6. Fits an account-level weather model.
        7. Calculates EUI and seasonal energy signatures.
        8. Runs PCA and K-means clustering for occupied/building meters with GSF > 0.
        9. Creates an investigation-priority score.
        10. Exports the results to Excel.

        **Important:** The PCA/anomaly score is a screening tool, not a verified savings estimate.
        """
    )
    return


@app.cell
def _(mo):
    bill_file = mo.ui.file(
        filetypes=[".xlsx"],
        label="Upload enriched FPL billing workbook",
        multiple=False,
    )
    bill_file
    return (bill_file,)


@app.cell
def _(bill_file, io, mo, pd):
    mo.stop(
        len(bill_file.value) == 0,
        mo.md("**Upload the FPL workbook above to continue.**"),
    )

    _uploaded = bill_file.value[0]

    bills_raw = pd.read_excel(
        io.BytesIO(_uploaded.contents),
        sheet_name="Enriched Bill History",
        dtype={"accountNumber": str},
    )

    mo.md(
        f"""
        **Loaded:** `{_uploaded.name}`  
        **Rows:** {len(bills_raw):,}
        """
    )
    return (bills_raw,)


@app.cell
def _(bills_raw, np, pd):
    _required = {"accountNumber", "periodStart", "periodEnd", "kWh"}
    _missing = _required - set(bills_raw.columns)
    if _missing:
        raise ValueError(
            "The 'Enriched Bill History' sheet is missing required columns: "
            + ", ".join(sorted(_missing))
        )

    bills = bills_raw.copy()

    bills["accountNumber"] = (
        bills["accountNumber"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
        .str.zfill(10)
    )

    for _col in ["periodStart", "periodEnd", "dateBilled"]:
        if _col in bills.columns:
            bills[_col] = pd.to_datetime(bills[_col], errors="coerce")

    bills["kWh"] = pd.to_numeric(bills["kWh"], errors="coerce")

    if "daysUsed" in bills.columns:
        bills["daysUsed"] = pd.to_numeric(bills["daysUsed"], errors="coerce")
    else:
        bills["daysUsed"] = np.nan

    _calculated_days = (bills["periodEnd"] - bills["periodStart"]).dt.days + 1
    bills["billing_days"] = bills["daysUsed"].where(
        bills["daysUsed"].gt(0),
        _calculated_days,
    )

    if "kWhPerDay" in bills.columns:
        bills["kWhPerDay"] = pd.to_numeric(bills["kWhPerDay"], errors="coerce")
    else:
        bills["kWhPerDay"] = np.nan

    bills["kWhPerDay"] = bills["kWhPerDay"].where(
        bills["kWhPerDay"].notna(),
        bills["kWh"] / bills["billing_days"],
    )

    bills = bills.dropna(
        subset=["accountNumber", "periodStart", "periodEnd", "kWh", "billing_days"]
    ).copy()

    bills = bills[
        (bills["periodEnd"] >= bills["periodStart"])
        & (bills["billing_days"] > 0)
    ].copy()

    bills = bills.sort_values(["accountNumber", "periodStart"]).reset_index(drop=True)

    bills.head()
    return (bills,)


@app.cell
def _(pd):
    # Complete account / GSF / chilled-water mapping supplied for the Daytona campus.
    _building_data = [
        ["101", 0, 0, "CORSAIR HALL PARKING LOT LIGHTS", "3800425260"],
        ["101", 17984, 1, "CORSAIR HALL", "8920081067"],
        ["150", 4400, 1, "NORTH TES, CAMPUS, PART 1", "2489797155"],
        ["150", 0, 1, "NORTH TES PART 2", "2583088048"],
        ["150", 0, 1, "NORTH TES PART 3", "0866970577"],
        ["155", 144411, 1, "RESIDENCE HALL 1", "9937144179"],
        ["201", 156309, 1, "NEW RESIDENCE HALL PHASE 2", "0923485197"],
        ["221", 61367, 1, "APOLLO HALL", "7649590390"],
        ["241", 62325, 1, "DOOLITTLE", "2175708953"],
        ["241", 0, 0, "COMPACTOR BLDG 241", "7479417052"],
        ["255", 192000, 1, "NEW RES 3", "4140510407"],
        ["259", 12743, 1, "CENTER FOR AVIATION SAFETY", "0597947423"],
        ["261", 33700, 1, "NEW FITNESS CENTER", "8281789027"],
        ["261", 0, 0, "NEW POOL PUMP", "5591473268"],
        ["267", 5200, 0, "CHAPEL", "6348091296"],
        ["311", 26941, 1, "SIMULATION CENTER", "0204486419"],
        ["312/320", 47950, 1, "FLEET MAINT HANGAR", "6817708222"],
        ["321", 57090, 1, "COLLEGE OF BUSINESS", "4728351455"],
        ["331", 20415, 1, "MILLER AUDITORIUM", "7272148268"],
        ["340", 48680, 1, "AMS LAB", "0698563160"],
        ["341", 75313, 1, "COLLEGE OF AVIATION", "5954141163"],
        ["417", 239172, 1, "PARKING GARAGE", "4092027129"],
        ["419", 134000, 1, "COLLEGE OF ARTS / SCIENCES", "0696189380"],
        ["501", 22276, 0, "ROTC BUILDING", "3836465256"],
        ["508", 0, 0, "ALUMNI ANNEX PARKING LOT LIGHTS", "5080503757"],
        ["508", 5608, 0, "ALUMNI ANNEX", "5129708953"],
        ["509", 6043.5, 0, "MOD 5 NORTH", "5355652131"],
        ["509", 6043.5, 0, "MOD 5 SOUTH", "6729115375"],
        ["510", 18214, 0, "EAGLE ALUMNI CENTER", "5130706988"],
        ["511", 0, 0, "CROTTY TENNIS / FOUNTAINS / FIELDS", "4104633310"],
        ["513", None, 0, "MOD 4 / MOD 513 TRAILER", "4553584584"],
        ["514/516", 1574, 0, "TRACK & FIELD", "2978169312"],
        ["520", None, 0, "PEB STORAGE UNIT", "1954501183"],
        ["557", 16913, 0, "NEX GEN PROJECT", "9214479546"],
        ["600", 0, 0, "CLYDE MORRIS BRIDGE", "2531584056"],
        ["601", 67559, 1, "ICI CENTER", "1258168226"],
        ["602", 0, 0, "WELCOME CENTER PARKING", "2167709944"],
        ["602", 42623, 1, "WELCOME CENTER", "4001977240"],
        ["605/607", 1990, 0, "SOCCER FACILITY / CONCESSIONS", "7226508096"],
        ["610", 193104, 1, "NEW STUDENT UNION", "7287874197"],
        ["610", 0, 0, "NEW STUDENT UNION LIFT STATION", "4737638413"],
        ["618", 127706, 1, "LEHMAN CENTER", "0970126587"],
        ["631", 4500, 1, "SOUTH TES", "5138663108"],
        ["631", 0, 1, "SOUTH TES 2", "5566426028"],
        ["641", 9996, 1, "S BUILDING ENGINEERING", "3117707905"],
        ["643", 14992, 0, "M BUILDING MECHANICAL ENGINEERING", "3111704957"],
        ["915", 0, 0, "FAC MGMT OUTDOOR LIGHTS", "5741531288"],
        ["917", 9008, 0, "FAC MGMT OFFICES", "5271977406"],
        ["915", 5000, 0, "FACILITIES MGMT SHOP", "9411911481"],
        ["919", 7551, 0, "PRINT SHOP", "3939215566"],
        ["921", 10083, 0, "ATMF", "8170573342"],
        ["923B", 2090, 0, "1501 BELLEVUE - MAINTENANCE BUILDING", "7332919047"],
        ["1103", 4121, 1, "1103 S CLYDE MORRIS - PUMP BUILDING", "1966352104"],
        ["1500", 263766, 1, "STUDENT VILLAGE", "4916435573"],
        ["1500", 0, 0, "STUDENT VILLAGE FIRE PUMP", "8567492015"],
        ["1501", 8305, 0, "1501 BELLEVUE AVENUE - BLDG 2", "4092392242"],
        ["1511", 0, 0, "MICAPLEX SIGN", "4219946003"],
        ["1511", 0, 0, "MICAPLEX LIFT STATION", "9412896533"],
        ["1511", 50975, 1, "MICAPLEX RESEARCH LAB", "6141586534"],
        ["1521", 17182, 1, "MICAPLEX RESEARCH PARK / WIND TUNNEL", "7352160357"],
        ["1525", 81547, 1, "AVIATION PKWY / CC & HYATT BROWN", "0748842101"],
        ["1527", 22411, 0, "RESEARCH PKWY CAT HANGAR", "8544186441"],
        ["1529", 34527, 1, "RESEARCH PKWY CAT II - SCIF", "9890440572"],
        ["1535", 18608, 0, "MICAPLEX HANGAR 1", "8337634359"],
        ["1575", 0, 0, "RP BALLFIELD WEST", "9622171164"],
        ["1575", 867, 0, "EAGLE FLIGHT STORAGE", "3434639237"],
        ["1600", 0, 0, "FLIGHT INSTRUCTOR SHED / HIGBY RAMP", "5016193541"],
        ["1624", 0, 0, "RICHARD PETTY BLVD LIGHTS", "6536994111"],
        ["1627", 5035, 0, "CHANUTE 1627", "4140806813"],
        ["1629", 5413, 0, "CHANUTE 1629", "4141804841"],
        ["1637", 5035, 0, "CHANUTE 1637", "4135801894"],
        ["1649", 5035, 0, "CHANUTE 1649", "4127802884"],
        ["1657", 5035, 0, "CHANUTE 1657", "4132807803"],
        ["1665", 5035, 0, "CHANUTE 1665", "4133805830"],
        ["2315", 7768, 0, "2315 BEVILLE ROAD", "9711303488"],
        ["2339", 17456, 0, "IT BUILDING 2339 BEVILLE ROAD", "8084637308"],
        ["2359", 13949, 0, "ICI BLDG 2359 BEVILLE ROAD", "9314692360"],
        ["2399", 18018, 0, "WWHQ4 2399 BEVILLE ROAD", "8256715072"],
        ["250/260", 19830, 0, "TOMCAT ANNEX MODS 30-1 & 30-2", "0621260108"],
        ["500/502", 3200, 0, "HEALTH / DISABILITY SERVICES", "3104703974"],
    ]

    building_map = pd.DataFrame(
        _building_data,
        columns=["bldg", "gsf", "cw", "building_name", "accountNumber"],
    )

    building_map["accountNumber"] = (
        building_map["accountNumber"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(10)
    )
    building_map["gsf"] = pd.to_numeric(building_map["gsf"], errors="coerce")
    building_map["cw"] = pd.to_numeric(building_map["cw"], errors="coerce").fillna(0).astype(int)

    building_map
    return (building_map,)


@app.cell
def _(bills, building_map, mo):
    joined = bills.merge(
        building_map,
        on="accountNumber",
        how="left",
        validate="many_to_one",
    )

    _matched = joined["building_name"].notna().mean()
    mo.md(f"**Account-to-building mapping coverage:** {_matched:.1%}")
    return (joined,)


@app.cell
def _(joined, mo):
    _unmatched = (
        joined.loc[joined["building_name"].isna(), ["accountNumber"]]
        .drop_duplicates()
        .sort_values("accountNumber")
    )
    mo.vstack(
        [
            mo.md("### Unmatched FPL accounts"),
            _unmatched if len(_unmatched) else mo.md("All bill accounts matched the GSF table."),
        ]
    )
    return


@app.cell
def _(joined, mo, pd, requests):
    # Daytona Beach International Airport / ERAU vicinity.
    LATITUDE = 29.17351
    LONGITUDE = -81.07185
    TIMEZONE = "America/New_York"

    weather_start = joined["periodStart"].min().normalize()
    weather_end = joined["periodEnd"].max().normalize()

    _url = "https://archive-api.open-meteo.com/v1/archive"
    _params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": weather_start.strftime("%Y-%m-%d"),
        "end_date": weather_end.strftime("%Y-%m-%d"),
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m",
        "temperature_unit": "fahrenheit",
        "timezone": TIMEZONE,
    }

    try:
        _response = requests.get(_url, params=_params, timeout=120)
        _response.raise_for_status()
        _payload = _response.json()
    except requests.RequestException as _exc:
        raise RuntimeError(
            "Could not download Open-Meteo historical weather. "
            "Check your internet connection and try again."
        ) from _exc

    if "hourly" not in _payload:
        raise RuntimeError(f"Open-Meteo returned no hourly data: {_payload}")

    weather = pd.DataFrame(_payload["hourly"])

    _weather_required = {
        "time",
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
    }
    _weather_missing = _weather_required - set(weather.columns)
    if _weather_missing:
        raise RuntimeError(
            "Open-Meteo response is missing columns: "
            + ", ".join(sorted(_weather_missing))
        )

    weather["time"] = pd.to_datetime(weather["time"], errors="coerce")
    weather = weather.rename(
        columns={
            "temperature_2m": "temp_f",
            "relative_humidity_2m": "rh_pct",
            "dew_point_2m": "dewpoint_f",
        }
    )

    weather = weather.dropna(subset=["time", "temp_f"]).sort_values("time").reset_index(drop=True)

    mo.md(
        f"""
        ### Weather downloaded
        **Period:** {weather_start.date()} through {weather_end.date()}  
        **Hourly rows:** {len(weather):,}
        """
    )
    return LATITUDE, LONGITUDE, TIMEZONE, weather, weather_end, weather_start


@app.cell
def _(np, weather):
    weather_calc = weather.copy()

    weather_calc["cooling_degree_hour_65"] = np.maximum(
        weather_calc["temp_f"] - 65.0, 0.0
    )
    weather_calc["heating_degree_hour_65"] = np.maximum(
        65.0 - weather_calc["temp_f"], 0.0
    )

    weather_calc["humid_cooling_hour"] = (
        (weather_calc["temp_f"] >= 75.0)
        & (weather_calc["rh_pct"] >= 60.0)
    ).astype(int)

    _temp_c = (weather_calc["temp_f"] - 32.0) * 5.0 / 9.0
    _rh = weather_calc["rh_pct"].clip(lower=1.0, upper=100.0)

    # Stull (2011) approximate wet-bulb temperature.
    _wet_c = (
        _temp_c * np.arctan(0.151977 * np.sqrt(_rh + 8.313659))
        + np.arctan(_temp_c + _rh)
        - np.arctan(_rh - 1.676331)
        + 0.00391838 * (_rh ** 1.5) * np.arctan(0.023101 * _rh)
        - 4.686035
    )
    weather_calc["wetbulb_f"] = _wet_c * 9.0 / 5.0 + 32.0

    weather_calc.head()
    return (weather_calc,)


@app.cell
def _(pd, weather_calc):
    def summarize_weather_period(start_date, end_date):
        _start = pd.Timestamp(start_date)
        _end_exclusive = pd.Timestamp(end_date) + pd.Timedelta(days=1)

        _w = weather_calc[
            (weather_calc["time"] >= _start)
            & (weather_calc["time"] < _end_exclusive)
        ]

        if _w.empty:
            return pd.Series(
                {
                    "weather_hours": 0,
                    "mean_temp_f": float("nan"),
                    "max_temp_f": float("nan"),
                    "min_temp_f": float("nan"),
                    "mean_rh_pct": float("nan"),
                    "mean_dewpoint_f": float("nan"),
                    "mean_wetbulb_f": float("nan"),
                    "max_wetbulb_f": float("nan"),
                    "cdd65": float("nan"),
                    "hdd65": float("nan"),
                    "humid_cooling_hours": float("nan"),
                    "hours_above_80f": float("nan"),
                    "hours_above_90f": float("nan"),
                }
            )

        return pd.Series(
            {
                "weather_hours": len(_w),
                "mean_temp_f": _w["temp_f"].mean(),
                "max_temp_f": _w["temp_f"].max(),
                "min_temp_f": _w["temp_f"].min(),
                "mean_rh_pct": _w["rh_pct"].mean(),
                "mean_dewpoint_f": _w["dewpoint_f"].mean(),
                "mean_wetbulb_f": _w["wetbulb_f"].mean(),
                "max_wetbulb_f": _w["wetbulb_f"].max(),
                "cdd65": _w["cooling_degree_hour_65"].sum() / 24.0,
                "hdd65": _w["heating_degree_hour_65"].sum() / 24.0,
                "humid_cooling_hours": _w["humid_cooling_hour"].sum(),
                "hours_above_80f": (_w["temp_f"] >= 80.0).sum(),
                "hours_above_90f": (_w["temp_f"] >= 90.0).sum(),
            }
        )

    return (summarize_weather_period,)


@app.cell
def _(joined, np, pd, summarize_weather_period):
    _weather_features = joined.apply(
        lambda _row: summarize_weather_period(
            _row["periodStart"],
            _row["periodEnd"],
        ),
        axis=1,
    )

    analysis = pd.concat(
        [
            joined.reset_index(drop=True),
            _weather_features.reset_index(drop=True),
        ],
        axis=1,
    )

    analysis["cdd65_per_day"] = analysis["cdd65"] / analysis["billing_days"]
    analysis["hdd65_per_day"] = analysis["hdd65"] / analysis["billing_days"]
    analysis["humid_cooling_hours_per_day"] = (
        analysis["humid_cooling_hours"] / analysis["billing_days"]
    )

    analysis["kwh_per_sf_bill"] = np.where(
        analysis["gsf"].gt(0),
        analysis["kWh"] / analysis["gsf"],
        np.nan,
    )

    analysis.head()
    return (analysis,)


@app.cell
def _(LinearRegression, analysis, np, pd, r2_score):
    def fit_account_weather_models(_analysis):
        _model_rows = []
        _period_frames = []

        for _account, _group in _analysis.groupby("accountNumber"):
            _d = (
                _group.sort_values("periodStart")
                .dropna(
                    subset=[
                        "kWhPerDay",
                        "cdd65_per_day",
                        "hdd65_per_day",
                        "mean_dewpoint_f",
                    ]
                )
                .copy()
            )

            if len(_d) < 8:
                continue

            _X = _d[
                ["cdd65_per_day", "hdd65_per_day", "mean_dewpoint_f"]
            ].astype(float)
            _y = _d["kWhPerDay"].astype(float)

            # Skip degenerate series with no usage variation.
            if _y.nunique(dropna=True) < 2:
                continue

            _model = LinearRegression()
            _model.fit(_X, _y)

            _predicted = _model.predict(_X)
            _residual = _y.to_numpy() - _predicted
            _mean_usage = float(_y.mean())

            _model_rows.append(
                {
                    "accountNumber": _account,
                    "building_name": _d["building_name"].iloc[0],
                    "bldg": _d["bldg"].iloc[0],
                    "gsf": _d["gsf"].iloc[0],
                    "cw": _d["cw"].iloc[0],
                    "n_periods": len(_d),
                    "base_kwh_day": float(_model.intercept_),
                    "cdd_sensitivity": float(_model.coef_[0]),
                    "hdd_sensitivity": float(_model.coef_[1]),
                    "dewpoint_sensitivity": float(_model.coef_[2]),
                    "weather_r2": float(r2_score(_y, _predicted)),
                    "residual_std": float(np.std(_residual, ddof=1)),
                    "residual_cv": (
                        float(np.std(_residual, ddof=1) / _mean_usage)
                        if _mean_usage != 0
                        else np.nan
                    ),
                }
            )

            _temp = _d.copy()
            _temp["expected_kwh_day"] = _predicted
            _temp["residual_kwh_day"] = _residual
            _period_frames.append(_temp)

        _models = pd.DataFrame(_model_rows)

        if _period_frames:
            _periods = pd.concat(_period_frames, ignore_index=True)
        else:
            _periods = pd.DataFrame()

        return _models, _periods

    account_models, modeled_periods = fit_account_weather_models(analysis)

    account_models.head()
    return account_models, modeled_periods


@app.cell
def _(analysis, np, pd):
    def make_building_features(_analysis):
        _rows = []

        for _account, _group in _analysis.groupby("accountNumber"):
            _d = (
                _group.sort_values("periodStart")
                .dropna(subset=["kWhPerDay", "kWh"])
                .copy()
            )

            if len(_d) < 8:
                continue

            _mean_daily = float(_d["kWhPerDay"].mean())
            _gsf = pd.to_numeric(
                pd.Series([_d["gsf"].iloc[0]]),
                errors="coerce",
            ).iloc[0]

            _months = _d["periodEnd"].dt.month
            _summer = _d.loc[_months.isin([6, 7, 8, 9]), "kWhPerDay"].mean()
            _winter = _d.loc[_months.isin([12, 1, 2]), "kWhPerDay"].mean()
            _annual_kwh = float(_d["kWh"].sum())

            _rows.append(
                {
                    "accountNumber": _account,
                    "building_name": _d["building_name"].iloc[0],
                    "bldg": _d["bldg"].iloc[0],
                    "gsf": _gsf,
                    "cw": _d["cw"].iloc[0],
                    "n_bills": len(_d),
                    "annual_kwh": _annual_kwh,
                    "eui_kwh_sf": (
                        _annual_kwh / _gsf
                        if pd.notna(_gsf) and _gsf > 0
                        else np.nan
                    ),
                    "seasonal_cv": (
                        float(_d["kWhPerDay"].std(ddof=1) / _mean_daily)
                        if _mean_daily != 0
                        else np.nan
                    ),
                    "peakiness": (
                        float(_d["kWhPerDay"].max() / _mean_daily)
                        if _mean_daily != 0
                        else np.nan
                    ),
                    "summer_winter_ratio": (
                        float(_summer / _winter)
                        if pd.notna(_winter) and _winter != 0
                        else np.nan
                    ),
                }
            )

        return pd.DataFrame(_rows)

    building_features = make_building_features(analysis)
    building_features.head()
    return (building_features,)


@app.cell
def _(account_models, building_features, mo):
    _join_cols = ["accountNumber", "building_name", "bldg", "gsf", "cw"]

    building_signature = building_features.merge(
        account_models,
        on=_join_cols,
        how="inner",
        validate="one_to_one",
    )

    pca_buildings = building_signature[
        building_signature["gsf"].gt(0)
    ].copy()

    mo.md(
        f"""
        ### Modeling population
        **Weather-modeled accounts:** {len(account_models):,}  
        **Accounts with building GSF > 0 used in PCA:** {len(pca_buildings):,}
        """
    )
    return building_signature, pca_buildings


@app.cell
def _():
    PCA_FEATURES = [
        "eui_kwh_sf",
        "seasonal_cv",
        "peakiness",
        "summer_winter_ratio",
        "cdd_sensitivity",
        "hdd_sensitivity",
        "dewpoint_sensitivity",
        "weather_r2",
        "residual_cv",
    ]
    return (PCA_FEATURES,)


@app.cell
def _(PCA, PCA_FEATURES, StandardScaler, mo, np, pca_buildings):
    mo.stop(
        len(pca_buildings) < 3,
        mo.md(
            "**Not enough valid GSF buildings for PCA. "
            "At least 3 modeled buildings are required.**"
        ),
    )

    _pca_input = pca_buildings[PCA_FEATURES].copy()

    for _col in PCA_FEATURES:
        _pca_input[_col] = _pca_input[_col].replace([np.inf, -np.inf], np.nan)

        _median = _pca_input[_col].median()
        if pd_isna := bool(np.isnan(_median)):
            _pca_input[_col] = 0.0
        else:
            _pca_input[_col] = _pca_input[_col].fillna(_median)

    _scaler = StandardScaler()
    X_scaled = _scaler.fit_transform(_pca_input)

    _n_components = min(len(PCA_FEATURES), len(pca_buildings))
    pca_model = PCA(n_components=_n_components)
    pca_array = pca_model.fit_transform(X_scaled)

    return X_scaled, pca_array, pca_model


@app.cell
def _(PCA_FEATURES, np, pca_array, pca_buildings, pca_model, pd):
    explained_variance = pd.DataFrame(
        {
            "PC": [f"PC{_i + 1}" for _i in range(len(pca_model.explained_variance_ratio_))],
            "explained_variance": pca_model.explained_variance_ratio_,
            "cumulative_variance": np.cumsum(pca_model.explained_variance_ratio_),
        }
    )

    pca_scores = pca_buildings.reset_index(drop=True).copy()

    for _i in range(pca_array.shape[1]):
        pca_scores[f"PC{_i + 1}"] = pca_array[:, _i]

    pca_loadings = pd.DataFrame(
        pca_model.components_.T,
        index=PCA_FEATURES,
        columns=[f"PC{_i + 1}" for _i in range(pca_model.components_.shape[0])],
    ).reset_index(names="feature")

    explained_variance
    return explained_variance, pca_loadings, pca_scores


@app.cell
def _(KMeans, X_scaled, pd, silhouette_score):
    _n_samples = len(X_scaled)
    _max_k = min(6, _n_samples - 1)
    _tests = []

    if _max_k >= 2:
        for _k in range(2, _max_k + 1):
            _km = KMeans(n_clusters=_k, random_state=42, n_init=25)
            _labels = _km.fit_predict(X_scaled)
            _tests.append(
                {
                    "clusters": _k,
                    "silhouette": float(silhouette_score(X_scaled, _labels)),
                }
            )

    cluster_tests = pd.DataFrame(_tests)
    cluster_tests
    return (cluster_tests,)


@app.cell
def _(KMeans, X_scaled, cluster_tests, pca_scores):
    if len(cluster_tests):
        best_k = int(
            cluster_tests.loc[cluster_tests["silhouette"].idxmax(), "clusters"]
        )
    else:
        best_k = 1

    if best_k >= 2:
        _cluster_model = KMeans(
            n_clusters=best_k,
            random_state=42,
            n_init=50,
        )
        pca_scores["cluster"] = _cluster_model.fit_predict(X_scaled) + 1
    else:
        pca_scores["cluster"] = 1

    best_k
    return (best_k,)


@app.cell
def _(np, pca_scores):
    _distance_cols = [c for c in ["PC1", "PC2", "PC3"] if c in pca_scores.columns]

    pca_scores["pca_distance"] = np.sqrt(
        sum(pca_scores[_col] ** 2 for _col in _distance_cols)
    )

    def zscore_safe(_series):
        _s = _series.astype(float)
        _std = float(_s.std(ddof=1))
        if not np.isfinite(_std) or _std == 0:
            return _s * 0.0
        return (_s - _s.mean()) / _std

    pca_scores["z_pca_distance"] = zscore_safe(pca_scores["pca_distance"])
    pca_scores["z_residual_cv"] = zscore_safe(
        pca_scores["residual_cv"].replace([np.inf, -np.inf], np.nan).fillna(
            pca_scores["residual_cv"].median()
        )
    )
    pca_scores["z_bad_weather_fit"] = zscore_safe(
        1.0 - pca_scores["weather_r2"].clip(lower=0.0, upper=1.0)
    )

    pca_scores["investigation_score"] = (
        0.45 * pca_scores["z_pca_distance"]
        + 0.35 * pca_scores["z_residual_cv"]
        + 0.20 * pca_scores["z_bad_weather_fit"]
    )

    anomaly_ranking = (
        pca_scores.sort_values("investigation_score", ascending=False)
        .reset_index(drop=True)
        .copy()
    )
    anomaly_ranking["rank"] = anomaly_ranking.index + 1

    anomaly_ranking[
        [
            "rank",
            "bldg",
            "building_name",
            "eui_kwh_sf",
            "weather_r2",
            "residual_cv",
            "cluster",
            "investigation_score",
        ]
    ].head(15)
    return (anomaly_ranking,)


@app.cell
def _(mo):
    mo.md(
        """
        ## PCA map

        Buildings farther from the center have more unusual multivariate energy signatures.
        Labels are limited to the 15 buildings with the greatest PCA distance so the chart remains readable.
        """
    )
    return


@app.cell
def _(pca_scores, plt):
    _fig, _ax = plt.subplots(figsize=(11, 8))

    for _cluster_id, _group in pca_scores.groupby("cluster"):
        _ax.scatter(
            _group["PC1"],
            _group["PC2"],
            s=60,
            label=f"Cluster {_cluster_id}",
            alpha=0.75,
        )

    _label_data = pca_scores.nlargest(15, "pca_distance")

    for _, _row in _label_data.iterrows():
        _label = f"{_row['bldg']} {_row['building_name']}"
        _ax.annotate(
            _label,
            (_row["PC1"], _row["PC2"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )

    _ax.axhline(0, linewidth=0.7)
    _ax.axvline(0, linewidth=0.7)
    _ax.set_xlabel("PC1")
    _ax.set_ylabel("PC2")
    _ax.set_title("ERAU Daytona FPL Building Energy Signatures")
    _ax.legend()
    _ax.grid(alpha=0.2)
    _fig.tight_layout()

    _fig
    return


@app.cell
def _(anomaly_ranking, plt):
    _top = anomaly_ranking.head(15).copy()
    _top["label"] = (
        _top["bldg"].astype(str) + " - " + _top["building_name"].astype(str)
    )

    _fig2, _ax2 = plt.subplots(figsize=(10, 7))
    _ax2.barh(
        _top["label"][::-1],
        _top["investigation_score"][::-1],
    )
    _ax2.set_xlabel("Composite investigation score")
    _ax2.set_title("Top Energy Investigation Candidates")
    _fig2.tight_layout()

    _fig2
    return


@app.cell
def _(anomaly_ranking, mo):
    mo.vstack(
        [
            mo.md("## Top investigation candidates"),
            mo.ui.table(
                anomaly_ranking[
                    [
                        "rank",
                        "bldg",
                        "building_name",
                        "eui_kwh_sf",
                        "weather_r2",
                        "residual_cv",
                        "cluster",
                        "investigation_score",
                    ]
                ].head(20),
                selection=None,
            ),
        ]
    )
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Interpretation notes

        The investigation score is an **engineering screening indicator**, not a savings estimate.

        High scores can reflect legitimate specialized use as well as possible issues such as:

        - unusual operating schedules
        - process or research loads
        - central plant / TES operation
        - occupancy changes
        - construction
        - meter assignment problems
        - controls overrides
        - equipment degradation
        """
    )
    return


@app.cell
def _(
    account_models,
    analysis,
    anomaly_ranking,
    building_signature,
    cluster_tests,
    explained_variance,
    io,
    mo,
    modeled_periods,
    pca_loadings,
    pca_scores,
    pd,
    weather_calc,
):
    _output = io.BytesIO()

    with pd.ExcelWriter(_output, engine="openpyxl") as _writer:
        analysis.to_excel(
            _writer,
            sheet_name="Billing Weather Model",
            index=False,
        )
        weather_calc.to_excel(
            _writer,
            sheet_name="Hourly Weather",
            index=False,
        )
        account_models.to_excel(
            _writer,
            sheet_name="Weather Models",
            index=False,
        )
        modeled_periods.to_excel(
            _writer,
            sheet_name="Modeled Periods",
            index=False,
        )
        building_signature.to_excel(
            _writer,
            sheet_name="Building Signatures",
            index=False,
        )
        pca_scores.to_excel(
            _writer,
            sheet_name="PCA Scores",
            index=False,
        )
        pca_loadings.to_excel(
            _writer,
            sheet_name="PCA Loadings",
            index=False,
        )
        explained_variance.to_excel(
            _writer,
            sheet_name="Explained Variance",
            index=False,
        )
        cluster_tests.to_excel(
            _writer,
            sheet_name="Cluster Tests",
            index=False,
        )
        anomaly_ranking.to_excel(
            _writer,
            sheet_name="Anomaly Ranking",
            index=False,
        )

    _output.seek(0)

    mo.download(
        data=_output.getvalue(),
        filename="ERAU_FPL_weather_PCA_results.xlsx",
        label="Download PCA results workbook",
    )
    return


if __name__ == "__main__":
    app.run()
