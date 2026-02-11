import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import schema


def analyze_temporal_data():
    csv_path = "output/SmartHarvest_DataCube_Temporal.csv"
    if not os.path.exists(csv_path):
        # Fallback: find latest SmartHarvest_*.csv in output/
        candidates = []
        for root, _, files in os.walk("output"):
            for f in files:
                if f.startswith("SmartHarvest_") and f.endswith(".csv") and "ready_for_kmeans" not in f:
                    candidates.append(os.path.join(root, f))
        if candidates:
            csv_path = max(candidates, key=os.path.getmtime)
            print(f"Default CSV not found. Using latest: {csv_path}")
        else:
            print(f"Error: {csv_path} not found and no fallback CSVs found.")
            return

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    df = schema.normalize_columns(df)

    # Drop system:index and .geo for analysis
    cols_to_drop = ["system:index", ".geo"]
    df_analysis = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

    report_lines = []
    report_lines.append("# SmartHarvest Temporal Data Validation Report")
    report_lines.append(f"**File:** `{csv_path}`")
    report_lines.append(f"**Rows:** {len(df)}")
    report_lines.append(f"**Columns:** {list(df_analysis.columns)}")
    report_lines.append("")

    # 1. Descriptive Statistics
    report_lines.append("## 1. Descriptive Statistics")
    stats = df_analysis.describe().T
    report_lines.append("```")
    report_lines.append(stats.to_string())
    report_lines.append("```")
    report_lines.append("")

    # 2. Plausibility Checks
    report_lines.append("## 2. Plausibility Checks")

    # NDVI Delta
    if "NDVI_Delta" in df.columns:
        ndvi_delta_mean = df["NDVI_Delta"].mean()
        report_lines.append(
            f"- **NDVI Delta Mean:** {ndvi_delta_mean:.4f} (Expected: close to 0 or slightly negative for senescence)"
        )
        if abs(ndvi_delta_mean) > 0.5:
            report_lines.append("  - ⚠️ **Warning:** NDVI Delta mean is unusually high/low.")
        else:
            report_lines.append("  - ✅ Plausible range.")
    else:
        report_lines.append("- **NDVI Delta Mean:** N/A (column missing)")

    # VH Drop
    if "VH_Drop" in df.columns:
        vh_drop_mean = df["VH_Drop"].mean()
        report_lines.append(f"- **VH Drop Mean:** {vh_drop_mean:.4f} dB (Positive = Structure Loss/Drying)")
    else:
        report_lines.append("- **VH Drop Mean:** N/A (column missing)")

    # Insolation
    if "Insolation" in df.columns:
        insolation_mean = df["Insolation"].mean()
        report_lines.append(f"- **Insolation Mean:** {insolation_mean:.4f} (Slope * cos(Aspect))")
    else:
        report_lines.append("- **Insolation Mean:** N/A (column missing)")

    # LST
    lst_col = schema.find_first_column(df, ["LST", "LST_Mean"])
    if lst_col:
        lst_mean = df[lst_col].mean()
        report_lines.append(f"- **{lst_col} Mean:** {lst_mean:.2f} °C")
        if lst_mean < 0 or lst_mean > 50:
            report_lines.append("  - ⚠️ **Warning:** LST mean is out of expected range (0-50°C).")
        else:
            report_lines.append("  - ✅ Plausible range.")
    else:
        report_lines.append("- **LST Mean:** N/A (column missing)")

    report_lines.append("")

    # 3. Correlations
    report_lines.append("## 3. Correlation Matrix (Top Features)")
    corr = df_analysis.corr()
    # Select key features
    key_features = [
        "NDVI_Peak",
        "NDVI_Delta",
        "VH_Late",
        "VH_Drop",
        "Insolation",
        "LST_Mean",
        "LST",
        "Slope",
    ]
    key_features = [f for f in key_features if f in df_analysis.columns]
    corr_key = corr.loc[key_features, key_features]
    report_lines.append("```")
    report_lines.append(corr_key.round(2).to_string())
    report_lines.append("```")
    report_lines.append("")

    # 4. Distributions (Histograms)
    print("Generating histograms...")
    features_to_plot = ["NDVI_Delta", "VH_Drop", "Insolation", "LST_Mean", "LST"]
    features_to_plot = [f for f in features_to_plot if f in df_analysis.columns]

    fig, axes = plt.subplots(1, len(features_to_plot), figsize=(15, 4))
    if len(features_to_plot) == 1:
        axes = [axes]

    for i, col in enumerate(features_to_plot):
        sns.histplot(df[col], kde=True, ax=axes[i])
        axes[i].set_title(f"{col} Distribution")

    plt.tight_layout()
    plt.savefig("output/temporal_distributions.png")
    report_lines.append("## 4. Distributions")
    report_lines.append("![Distributions](temporal_distributions.png)")

    # Save Report
    with open("output/DATA_VALIDATION_REPORT.md", "w") as f:
        f.write("\n".join(report_lines))

    print("Validation complete. Report saved to DATA_VALIDATION_REPORT.md")


if __name__ == "__main__":
    analyze_temporal_data()
