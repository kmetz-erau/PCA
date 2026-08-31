import marimo

__generated_with = "0.17.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import io
    import re
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
        re,
        requests,
        silhouette_score,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        # Prescott AiM Building-Only Electric PCA

        This notebook reproduces the building-only Prescott analysis:

        1. Upload the AiM meter-reading CSV.
        2. Keep electric meters only and convert KWH/MWH/GWH to kWh.
        3. Exclude chillers, athletic lighting, field lighting, roadway lighting, plots, and infrastructure meters.
        4. Use the most recent 36 months.
        5. Pull **actual Prescott historical weather** from Open-Meteo and calculate monthly HDD65/CDD65.
        6. Fit a simple weather model to each building meter.
        7. Remove the fitted weather component to create a weather-adjusted monthly load shape.
        8. Run PCA on the weather-adjusted load shapes.
        9. Test K-means cluster counts.
        10. Create meter/data-quality flags and an investigation ranking.

        **Important:** PCA distance means *different*, not automatically *inefficient*.
        """
    )
    return


@app.cell
def _(mo):
    csv_file = mo.ui.file(
        filetypes=[".csv"],
        label="Upload AiM meter readings CSV",
        multiple=False,
    )
    csv_file
    return (csv_file,)


@app.cell
def _(csv_file, io, mo, pd):
    mo.stop(
        len(csv_file.value) == 0,
        mo.md("**Upload the AiM CSV above to continue.**"),
    )

    _uploaded = csv_file.value[0]
    raw = pd.read_csv(io.BytesIO(_uploaded.contents))

    _required = {"Meter", "UOM", "Reading Date", "Usage"}
    _missing = _required - set(raw.columns)
    if _missing:
        raise ValueError(
            "CSV is missing required columns: " + ", ".join(sorted(_missing))
        )

    mo.md(
        f"""
        **Loaded:** `{_uploaded.name}`  
        **Rows:** {len(raw):,}  
        **Meters:** {raw['Meter'].nunique():,}
        """
    )
    return (raw,)


@app.cell
def _(np, pd, raw):
    def parse_number(_series):
        _s = _series.astype(str).str.strip()
        _neg = _s.str.match(r"^\(.*\)$", na=False)
        _s = _s.str.replace(",", "", regex=False)
        _s = _s.str.replace("(", "", regex=False).str.replace(")", "", regex=False)
        _out = pd.to_numeric(_s, errors="coerce")
        _out.loc[_neg] = -_out.loc[_neg].abs()
        return _out

    clean = raw.copy()
    clean["Meter"] = clean["Meter"].astype(str).str.strip()
    clean["UOM"] = clean["UOM"].astype(str).str.strip().str.upper()
    clean["Reading Date"] = pd.to_datetime(clean["Reading Date"], errors="coerce")
    clean["Usage_numeric"] = parse_number(clean["Usage"])

    _electric_multiplier = {"KWH": 1.0, "MWH": 1000.0, "GWH": 1_000_000.0}
    electric = clean[clean["UOM"].isin(_electric_multiplier)].copy()
    electric["kWh"] = electric["Usage_numeric"] * electric["UOM"].map(_electric_multiplier)
    electric["month"] = electric["Reading Date"].dt.to_period("M").dt.to_timestamp()

    electric = electric.dropna(subset=["Meter", "Reading Date", "month", "kWh"])
    electric = electric.sort_values(["Meter", "Reading Date"]).reset_index(drop=True)

    electric.head()
    return clean, electric, parse_number


@app.cell
def _(electric, mo):
    mo.md(
        f"""
        ### Electric-meter population
        **Electric rows:** {len(electric):,}  
        **Electric meters:** {electric['Meter'].nunique():,}
        """
    )
    return


@app.cell
def _(mo):
    # Default exclusions used for the building-only Prescott peer analysis.
    exclusion_text = mo.ui.text_area(
        value="""CHILLER
SOCCER
TENNIS
INTFLD
SOFTBALL
RDWY
A-F-PLOTS
3-CABLE
T1.1
T2.1
TBC.1""",
        label="Exclude meters containing any of these terms (one per line)",
        full_width=True,
        rows=12,
    )
    exclusion_text
    return (exclusion_text,)


@app.cell
def _(electric, exclusion_text, re):
    _terms = [x.strip() for x in exclusion_text.value.splitlines() if x.strip()]
    _pattern = "|".join(re.escape(x) for x in _terms)

    if _pattern:
        _exclude_mask = electric["Meter"].str.contains(
            _pattern, case=False, regex=True, na=False
        )
    else:
        _exclude_mask = False

    building_electric = electric.loc[~_exclude_mask].copy()
    excluded_electric = electric.loc[_exclude_mask].copy()

    return building_electric, excluded_electric


@app.cell
def _(building_electric, excluded_electric, mo):
    _excluded_names = sorted(excluded_electric["Meter"].dropna().unique())
    mo.vstack(
        [
            mo.md(
                f"""
                ### Building-only filter
                **Building electric meters retained:** {building_electric['Meter'].nunique()}  
                **Specialty/infrastructure meters excluded:** {len(_excluded_names)}
                """
            ),
            mo.ui.table({"Excluded meter": _excluded_names}, selection=None),
        ]
    )
    return


@app.cell
def _(building_electric, pd):
    # Aggregate to one monthly observation per meter.
    monthly = (
        building_electric.groupby(["Meter", "month"], as_index=False)
        .agg(kWh=("kWh", "sum"))
        .sort_values(["Meter", "month"])
    )

    _max_month = monthly["month"].max()
    _start_month = (_max_month.to_period("M") - 35).to_timestamp()

    monthly_36 = monthly[
        (monthly["month"] >= _start_month) & (monthly["month"] <= _max_month)
    ].copy()

    ANALYSIS_START = _start_month
    ANALYSIS_END = _max_month

    return ANALYSIS_END, ANALYSIS_START, monthly, monthly_36


@app.cell
def _(ANALYSIS_END, ANALYSIS_START, mo, monthly_36):
    _coverage = (
        monthly_36.groupby("Meter")["month"]
        .nunique()
        .sort_values(ascending=False)
    )
    mo.md(
        f"""
        ### Analysis window
        **Start:** {ANALYSIS_START:%B %Y}  
        **End:** {ANALYSIS_END:%B %Y}  
        **Months:** 36  
        **Meters with at least 30 months:** {(_coverage >= 30).sum()}
        """
    )
    return


@app.cell
def _(ANALYSIS_END, ANALYSIS_START, mo, pd, requests):
    # Prescott Regional Airport / Prescott, Arizona vicinity.
    LATITUDE = 34.6492
    LONGITUDE = -112.4196

    # Pull daily mean temperature and compute monthly HDD65/CDD65.
    _weather_url = "https://archive-api.open-meteo.com/v1/archive"
    _end_date = (ANALYSIS_END + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    _params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": ANALYSIS_START.strftime("%Y-%m-%d"),
        "end_date": _end_date,
        "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "America/Phoenix",
    }

    try:
        _response = requests.get(_weather_url, params=_params, timeout=120)
        _response.raise_for_status()
        _payload = _response.json()
    except requests.RequestException as _exc:
        raise RuntimeError(
            "Could not download Prescott weather from Open-Meteo. "
            "Check internet access and rerun the weather cell."
        ) from _exc

    if "daily" not in _payload:
        raise RuntimeError(f"Open-Meteo returned no daily data: {_payload}")

    daily_weather = pd.DataFrame(_payload["daily"])
    daily_weather["date"] = pd.to_datetime(daily_weather["time"], errors="coerce")
    daily_weather["month"] = daily_weather["date"].dt.to_period("M").dt.to_timestamp()
    daily_weather["HDD65"] = (65.0 - daily_weather["temperature_2m_mean"]).clip(lower=0)
    daily_weather["CDD65"] = (daily_weather["temperature_2m_mean"] - 65.0).clip(lower=0)

    weather_monthly = (
        daily_weather.groupby("month", as_index=False)
        .agg(
            HDD65=("HDD65", "sum"),
            CDD65=("CDD65", "sum"),
            mean_temp_f=("temperature_2m_mean", "mean"),
            max_temp_f=("temperature_2m_max", "max"),
            min_temp_f=("temperature_2m_min", "min"),
            weather_days=("date", "count"),
        )
        .sort_values("month")
    )

    mo.md(
        f"**Weather months downloaded:** {len(weather_monthly)} from Prescott, Arizona"
    )
    return LATITUDE, LONGITUDE, daily_weather, weather_monthly


@app.cell
def _(monthly_36, weather_monthly):
    meter_weather = monthly_36.merge(
        weather_monthly,
        on="month",
        how="left",
        validate="many_to_one",
    )
    meter_weather.head()
    return (meter_weather,)


@app.cell
def _(LinearRegression, meter_weather, np, pd, r2_score):
    def fit_weather_models(_data):
        _rows = []
        _periods = []

        for _meter, _group in _data.groupby("Meter"):
            _d = (
                _group.dropna(subset=["kWh", "HDD65", "CDD65"])
                .sort_values("month")
                .copy()
            )

            if len(_d) < 24 or _d["kWh"].nunique() < 2:
                continue

            _X = _d[["HDD65", "CDD65"]].astype(float)
            _y = _d["kWh"].astype(float)

            _model = LinearRegression()
            _model.fit(_X, _y)
            _pred = _model.predict(_X)
            _resid = _y.to_numpy() - _pred
            _mean = float(_y.mean())

            _rows.append(
                {
                    "Meter": _meter,
                    "n_months": len(_d),
                    "mean_monthly_kwh": _mean,
                    "weather_base_kwh": float(_model.intercept_),
                    "hdd_sensitivity_kwh_per_hdd": float(_model.coef_[0]),
                    "cdd_sensitivity_kwh_per_cdd": float(_model.coef_[1]),
                    "weather_r2": float(r2_score(_y, _pred)),
                    "residual_std_kwh": float(np.std(_resid, ddof=1)),
                    "residual_cv": (
                        float(np.std(_resid, ddof=1) / _mean)
                        if _mean != 0
                        else np.nan
                    ),
                }
            )

            _temp = _d.copy()
            _temp["expected_weather_kwh"] = _pred
            _temp["weather_residual_kwh"] = _resid
            _temp["weather_adjusted_index"] = 1.0 + (_resid / _mean if _mean != 0 else 0.0)
            _periods.append(_temp)

        return (
            pd.DataFrame(_rows),
            pd.concat(_periods, ignore_index=True) if _periods else pd.DataFrame(),
        )

    weather_models, adjusted_months = fit_weather_models(meter_weather)
    return adjusted_months, weather_models


@app.cell
def _(adjusted_months, pd):
    # Data quality / stability features from raw monthly usage.
    def make_quality_features(_data):
        _rows = []
        for _meter, _group in _data.groupby("Meter"):
            _d = _group.sort_values("month").copy()
            _usage = _d["kWh"].astype(float)
            _positive = _usage[_usage > 0]

            _pct = _usage.pct_change(fill_method=None).replace([float("inf"), float("-inf")], pd.NA)
            _abs_pct = pd.to_numeric(_pct.abs(), errors="coerce")

            _median_pos = _positive.median() if len(_positive) else float("nan")
            _max_to_median = (
                _usage.max() / _median_pos
                if pd.notna(_median_pos) and _median_pos > 0
                else float("nan")
            )

            _rows.append(
                {
                    "Meter": _meter,
                    "zero_months": int((_usage == 0).sum()),
                    "negative_months": int((_usage < 0).sum()),
                    "max_abs_monthly_pct_change": float(_abs_pct.max()) if _abs_pct.notna().any() else float("nan"),
                    "max_to_median_ratio": float(_max_to_median),
                    "raw_cv": float(_usage.std(ddof=1) / _usage.mean()) if _usage.mean() != 0 else float("nan"),
                }
            )
        return pd.DataFrame(_rows)

    quality_features = make_quality_features(adjusted_months)
    return (quality_features,)


@app.cell
def _(adjusted_months, pd):
    # Require at least 30 of the 36 monthly observations.
    _coverage = adjusted_months.groupby("Meter")["month"].nunique()
    valid_meters = _coverage[_coverage >= 30].index

    pca_months = adjusted_months[adjusted_months["Meter"].isin(valid_meters)].copy()

    pca_matrix = pca_months.pivot_table(
        index="Meter",
        columns="month",
        values="weather_adjusted_index",
        aggfunc="mean",
    ).sort_index(axis=1)

    # Fill isolated missing months with the meter's own median adjusted index.
    pca_matrix = pca_matrix.apply(lambda _row: _row.fillna(_row.median()), axis=1)

    return pca_matrix, pca_months, valid_meters


@app.cell
def _(PCA, StandardScaler, np, pca_matrix):
    _scaler = StandardScaler()
    X_scaled = _scaler.fit_transform(pca_matrix)

    _n_components = min(pca_matrix.shape[0], pca_matrix.shape[1])
    pca_model = PCA(n_components=_n_components)
    pca_array = pca_model.fit_transform(X_scaled)

    return X_scaled, pca_array, pca_model


@app.cell
def _(np, pca_array, pca_matrix, pca_model, pd):
    explained_variance = pd.DataFrame(
        {
            "PC": [f"PC{_i + 1}" for _i in range(len(pca_model.explained_variance_ratio_))],
            "explained_variance": pca_model.explained_variance_ratio_,
            "cumulative_variance": np.cumsum(pca_model.explained_variance_ratio_),
        }
    )

    pca_scores = pd.DataFrame({"Meter": pca_matrix.index}).reset_index(drop=True)
    for _i in range(pca_array.shape[1]):
        pca_scores[f"PC{_i + 1}"] = pca_array[:, _i]

    pca_loadings = pd.DataFrame(
        pca_model.components_.T,
        index=[_c.strftime("%Y-%m") for _c in pca_matrix.columns],
        columns=[f"PC{_i + 1}" for _i in range(pca_model.components_.shape[0])],
    ).reset_index(names="month")

    explained_variance.head(12)
    return explained_variance, pca_loadings, pca_scores


@app.cell
def _(KMeans, X_scaled, pd, silhouette_score):
    _tests = []
    _max_k = min(6, len(X_scaled) - 1)

    for _k in range(2, _max_k + 1):
        _model = KMeans(n_clusters=_k, random_state=42, n_init=50)
        _labels = _model.fit_predict(X_scaled)
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
        best_k = int(cluster_tests.loc[cluster_tests["silhouette"].idxmax(), "clusters"])
        _km = KMeans(n_clusters=best_k, random_state=42, n_init=50)
        pca_scores["cluster"] = _km.fit_predict(X_scaled) + 1
    else:
        best_k = 1
        pca_scores["cluster"] = 1

    best_k
    return (best_k,)


@app.cell
def _(np, pca_scores, quality_features, weather_models):
    _pc_cols = [c for c in ["PC1", "PC2", "PC3"] if c in pca_scores.columns]
    pca_scores["pca_distance"] = np.sqrt(
        sum(pca_scores[_c] ** 2 for _c in _pc_cols)
    )

    ranking = (
        pca_scores.merge(weather_models, on="Meter", how="left")
        .merge(quality_features, on="Meter", how="left")
    )

    def percentile(_series, higher_is_worse=True):
        _s = _series.astype(float)
        _pct = _s.rank(pct=True, method="average")
        return _pct if higher_is_worse else 1.0 - _pct

    ranking["pca_distance_pct"] = percentile(ranking["pca_distance"], True)
    ranking["residual_cv_pct"] = percentile(ranking["residual_cv"].fillna(ranking["residual_cv"].median()), True)
    ranking["low_weather_fit_pct"] = percentile(ranking["weather_r2"].fillna(0), False)

    # Data-quality risk: extreme changes, spikes, zeros, or negatives.
    _jump = ranking["max_abs_monthly_pct_change"].replace([np.inf, -np.inf], np.nan).fillna(0)
    _spike = ranking["max_to_median_ratio"].replace([np.inf, -np.inf], np.nan).fillna(0)
    ranking["data_quality_risk"] = (
        0.45 * percentile(_jump, True)
        + 0.35 * percentile(_spike, True)
        + 0.10 * (ranking["zero_months"] > 0).astype(float)
        + 0.10 * (ranking["negative_months"] > 0).astype(float)
    )

    # Operational screen. Keep data-quality risk separate so a bad meter does not
    # automatically become an energy-efficiency finding.
    ranking["operational_score"] = 100 * (
        0.50 * ranking["pca_distance_pct"]
        + 0.30 * ranking["residual_cv_pct"]
        + 0.20 * ranking["low_weather_fit_pct"]
    )

    ranking["review_type"] = np.where(
        ranking["data_quality_risk"] >= 0.75,
        "Meter/data QA first",
        "Operational review",
    )

    ranking = ranking.sort_values(
        ["operational_score", "data_quality_risk"], ascending=[False, False]
    ).reset_index(drop=True)
    ranking["rank"] = ranking.index + 1

    return (ranking,)


@app.cell
def _(mo, ranking):
    _cols = [
        "rank",
        "Meter",
        "operational_score",
        "review_type",
        "weather_r2",
        "residual_cv",
        "pca_distance",
        "max_abs_monthly_pct_change",
        "max_to_median_ratio",
        "cluster",
    ]
    mo.vstack(
        [
            mo.md("## Top building investigation candidates"),
            mo.ui.table(ranking[_cols].head(20), selection=None),
        ]
    )
    return


@app.cell
def _(explained_variance, mo):
    _first3 = explained_variance.head(3)["explained_variance"].sum()
    _n85 = int((explained_variance["cumulative_variance"] < 0.85).sum() + 1)
    mo.md(
        f"""
        ## PCA summary
        **PC1:** {explained_variance.iloc[0]['explained_variance']:.1%}  
        **PC2:** {explained_variance.iloc[1]['explained_variance']:.1%}  
        **PC3:** {explained_variance.iloc[2]['explained_variance']:.1%}  
        **First 3 PCs:** {_first3:.1%}  
        **PCs required for 85% variance:** {_n85}
        """
    )
    return


@app.cell
def _(pca_scores, plt):
    _fig, _ax = plt.subplots(figsize=(11, 8))

    for _cluster, _g in pca_scores.groupby("cluster"):
        _ax.scatter(
            _g["PC1"],
            _g["PC2"],
            s=60,
            alpha=0.75,
            label=f"Cluster {_cluster}",
        )

    _labels = pca_scores.nlargest(min(15, len(pca_scores)), "pca_distance")
    for _, _row in _labels.iterrows():
        _ax.annotate(
            _row["Meter"],
            (_row["PC1"], _row["PC2"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )

    _ax.axhline(0, linewidth=0.7)
    _ax.axvline(0, linewidth=0.7)
    _ax.set_xlabel("PC1")
    _ax.set_ylabel("PC2")
    _ax.set_title("Prescott Building-Only Weather-Adjusted Electric PCA")
    _ax.legend()
    _ax.grid(alpha=0.2)
    _fig.tight_layout()
    _fig
    return


@app.cell
def _(pca_loadings, plt):
    _show = pca_loadings[["month", "PC1", "PC2", "PC3"]].copy()
    _fig2, _ax2 = plt.subplots(figsize=(13, 6))
    _x = range(len(_show))
    _ax2.plot(_x, _show["PC1"], marker="o", label="PC1")
    _ax2.plot(_x, _show["PC2"], marker="o", label="PC2")
    _ax2.plot(_x, _show["PC3"], marker="o", label="PC3")
    _ax2.set_xticks(list(_x))
    _ax2.set_xticklabels(_show["month"], rotation=90)
    _ax2.set_ylabel("PCA loading")
    _ax2.set_title("Monthly PCA Loadings")
    _ax2.legend()
    _ax2.grid(alpha=0.2)
    _fig2.tight_layout()
    _fig2
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## How to interpret the output

        - **High PCA distance**: the meter's weather-adjusted load shape differs from peer buildings.
        - **Low weather R²**: HDD/CDD do not explain much of the meter's monthly variation.
        - **High residual CV**: usage remains volatile after weather adjustment.
        - **Meter/data QA first**: the history contains unusually large jumps, spikes, zeros, or negative usage and should be validated before calling it an energy opportunity.
        - **Operational review**: unusual behavior remains without a severe data-quality flag; these are better candidates for schedule/BAS/occupancy review.

        For Prescott, HDD is often materially important. Chillers and outdoor/sports lighting are deliberately excluded because they should be analyzed as separate peer groups.
        """
    )
    return


@app.cell
def _(
    adjusted_months,
    cluster_tests,
    daily_weather,
    electric,
    excluded_electric,
    explained_variance,
    io,
    mo,
    pca_loadings,
    pca_matrix,
    pca_scores,
    pd,
    quality_features,
    ranking,
    weather_models,
    weather_monthly,
):
    _buffer = io.BytesIO()
    with pd.ExcelWriter(_buffer, engine="openpyxl") as _writer:
        electric.to_excel(_writer, sheet_name="Electric Raw Cleaned", index=False)
        excluded_electric[["Meter"]].drop_duplicates().sort_values("Meter").to_excel(
            _writer, sheet_name="Excluded Meters", index=False
        )
        weather_monthly.to_excel(_writer, sheet_name="Monthly Weather", index=False)
        daily_weather.to_excel(_writer, sheet_name="Daily Weather", index=False)
        adjusted_months.to_excel(_writer, sheet_name="Weather Adjusted Months", index=False)
        weather_models.to_excel(_writer, sheet_name="Weather Models", index=False)
        quality_features.to_excel(_writer, sheet_name="Data Quality", index=False)
        pca_matrix.reset_index().to_excel(_writer, sheet_name="PCA Matrix", index=False)
        pca_scores.to_excel(_writer, sheet_name="PCA Scores", index=False)
        pca_loadings.to_excel(_writer, sheet_name="PCA Loadings", index=False)
        explained_variance.to_excel(_writer, sheet_name="Explained Variance", index=False)
        cluster_tests.to_excel(_writer, sheet_name="Cluster Tests", index=False)
        ranking.to_excel(_writer, sheet_name="Investigation Ranking", index=False)

    _buffer.seek(0)
    mo.download(
        data=_buffer.getvalue(),
        filename="prescott_building_only_weather_pca.xlsx",
        label="Download Prescott PCA workbook",
    )
    return


if __name__ == "__main__":
    app.run()
