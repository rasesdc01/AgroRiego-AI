"""
AgroRiego AI — Preprocessing Pipeline (Zero Temporal Leakage)
Reads unaltered raw EcoIrrigate CSV from datasets/raw/ and builds
chronological train/val/test datasets with lagged, rolling, and horizon targets.
"""

import json
import os
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_PATH = os.path.join(ROOT, "datasets", "raw", "kolkata_unified_dataset.csv")
PROCESSED_DIR = os.path.join(ROOT, "datasets", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)


def build_features_for_farm(df_farm: pd.DataFrame) -> pd.DataFrame:
    df = df_farm.sort_values("Timestamp").reset_index(drop=True).copy()

    # Physical engineered features (strictly at time t or past <= t)
    df["temp_gradient_c"] = df["Atm_Temperature_C"] - df["Soil_Temperature_C"]
    df["board_soil_temp_diff_c"] = df["Sensor_Board_Temperature_C"] - df["Soil_Temperature_C"]

    # Past lags (15-min steps: 1=15m, 4=1h, 16=4h, 24=6h, 48=12h, 96=24h)
    for lag_steps, label in [(1, "15m"), (4, "1h"), (16, "4h"), (24, "6h"), (48, "12h"), (96, "24h")]:
        df[f"vwc_lag_{label}"] = df["Volumetric_Moisture_Pct"].shift(lag_steps)
        df[f"adc_lag_{label}"] = df["Raw_Capacitive_ADC"].shift(lag_steps)
        df[f"soil_temp_lag_{label}"] = df["Soil_Temperature_C"].shift(lag_steps)

    # Past rolling statistics (strictly causal)
    df["vwc_rolling_mean_4h"] = df["Volumetric_Moisture_Pct"].rolling(window=16, min_periods=16).mean()
    df["vwc_rolling_std_4h"] = df["Volumetric_Moisture_Pct"].rolling(window=16, min_periods=16).std()
    df["vwc_rolling_mean_24h"] = df["Volumetric_Moisture_Pct"].rolling(window=96, min_periods=96).mean()
    df["vwc_rate_1h"] = df["Volumetric_Moisture_Pct"] - df["vwc_lag_1h"]
    df["vwc_rate_6h"] = df["Volumetric_Moisture_Pct"] - df["vwc_lag_6h"]
    df["atm_temp_rolling_mean_6h"] = df["Atm_Temperature_C"].rolling(window=24, min_periods=24).mean()

    # Future targets for Model 2 (1h=+4, 6h=+24, 12h=+48, 24h=+96 steps)
    df["target_vwc_1h"] = df["Volumetric_Moisture_Pct"].shift(-4)
    df["target_vwc_6h"] = df["Volumetric_Moisture_Pct"].shift(-24)
    df["target_vwc_12h"] = df["Volumetric_Moisture_Pct"].shift(-48)
    df["target_vwc_24h"] = df["Volumetric_Moisture_Pct"].shift(-96)

    # Target timestamps to enforce leakage-free chronological splitting
    df["target_ts_24h"] = df["Timestamp"].shift(-96)
    return df


def main():
    raw_df = pd.read_csv(RAW_PATH)
    raw_df["Timestamp"] = pd.to_datetime(raw_df["Timestamp"])

    train_parts, val_parts, test_parts = [], [], []
    farm_summaries = {}

    for farm_id, g in raw_df.groupby("Farm_ID"):
        feat_df = build_features_for_farm(g)
        valid_df = feat_df.dropna().reset_index(drop=True)

        n = len(valid_df)
        i_train_end = int(n * 0.70)
        i_val_end = int(n * 0.85)

        # Purged chronological split: drop rows whose 24h target timestamp crosses into next split
        val_start_ts = valid_df.loc[i_train_end, "Timestamp"]
        test_start_ts = valid_df.loc[i_val_end, "Timestamp"]

        tr = valid_df.iloc[:i_train_end]
        tr = tr[tr["target_ts_24h"] < val_start_ts].copy()

        va = valid_df.iloc[i_train_end:i_val_end]
        va = va[va["target_ts_24h"] < test_start_ts].copy()

        te = valid_df.iloc[i_val_end:].copy()

        tr["split"] = "train"
        va["split"] = "val"
        te["split"] = "test"

        train_parts.append(tr)
        val_parts.append(va)
        test_parts.append(te)

        farm_summaries[farm_id] = {
            "raw_rows": int(len(g)),
            "valid_windowed_rows": int(n),
            "train_rows": int(len(tr)),
            "val_rows": int(len(va)),
            "test_rows": int(len(te)),
            "train_period": [str(tr["Timestamp"].min()), str(tr["Timestamp"].max())],
            "val_period": [str(va["Timestamp"].min()), str(va["Timestamp"].max())],
            "test_period": [str(te["Timestamp"].min()), str(te["Timestamp"].max())],
        }

    train_df = pd.concat(train_parts, ignore_index=True).drop(columns=["target_ts_24h"])
    val_df = pd.concat(val_parts, ignore_index=True).drop(columns=["target_ts_24h"])
    test_df = pd.concat(test_parts, ignore_index=True).drop(columns=["target_ts_24h"])

    train_df.to_csv(os.path.join(PROCESSED_DIR, "train.csv"), index=False)
    val_df.to_csv(os.path.join(PROCESSED_DIR, "val.csv"), index=False)
    test_df.to_csv(os.path.join(PROCESSED_DIR, "test.csv"), index=False)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "source_dataset": "kolkata_unified_dataset.csv (EcoIrrigate, DOI: 10.17632/8x4v7yy3ds.1)",
        "total_train": int(len(train_df)),
        "total_val": int(len(val_df)),
        "total_test": int(len(test_df)),
        "purge_horizon_hours": 24,
        "farms": farm_summaries,
        "feature_columns_forecast": [
            "Volumetric_Moisture_Pct",
            "Raw_Capacitive_ADC",
            "Sensor_Board_Temperature_C",
            "Sensor_Voltage_V",
            "Atm_Pressure_inHg",
            "Atm_Temperature_C",
            "Soil_Temperature_C",
            "temp_gradient_c",
            "board_soil_temp_diff_c",
            "Hour_sin",
            "Hour_cos",
            "Day_sin",
            "Day_cos",
            "vwc_lag_15m",
            "vwc_lag_1h",
            "vwc_lag_4h",
            "vwc_lag_6h",
            "vwc_lag_12h",
            "vwc_lag_24h",
            "adc_lag_1h",
            "adc_lag_6h",
            "soil_temp_lag_1h",
            "soil_temp_lag_6h",
            "vwc_rolling_mean_4h",
            "vwc_rolling_std_4h",
            "vwc_rolling_mean_24h",
            "vwc_rate_1h",
            "vwc_rate_6h",
            "atm_temp_rolling_mean_6h",
        ],
        "feature_columns_calibration": [
            "Raw_Capacitive_ADC",
            "Sensor_Board_Temperature_C",
            "Sensor_Voltage_V",
            "Soil_Temperature_C",
            "Atm_Temperature_C",
            "Hour_sin",
            "Hour_cos",
        ],
    }

    with open(os.path.join(PROCESSED_DIR, "split_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    dict_md = """# Diccionario de Datos Procesados — AgroRiego AI

**Origen:** `datasets/raw/kolkata_unified_dataset.csv` (Saha et al., 2026, CC BY 4.0, DOI: `10.17632/8x4v7yy3ds.1`).  
**Regla anti-fuga temporal (*Zero Leakage*):** Todos los rezagos y estadísticas móviles se calcularon de forma estrictamente causal por `Farm_ID`. Se purgó la frontera de 24 horas (96 pasos) entre `train`, `val` y `test` para impedir que cualquier etiqueta futura de entrenamiento traslape el intervalo temporal de validación o prueba.

## Divisiones Cronológicas Generadas
- `train.csv`: {train} registros
- `val.csv`: {val} registros
- `test.csv`: {test} registros

## Variables de Ingeniería Adicionales
| Variable | Unidad | Fórmula / Definición | Propósito |
|---|---|---|---|
| `temp_gradient_c` | °C | `Atm_Temperature_C - Soil_Temperature_C` | Gradiente térmico atmósfera-suelo impulsor de evaporación |
| `board_soil_temp_diff_c` | °C | `Sensor_Board_Temperature_C - Soil_Temperature_C` | Corrección térmica de electrónica HW-390 |
| `vwc_lag_*` | % VWC | Valor de humedad en $t-1, t-4, t-16, t-24, t-48, t-96$ | Memoria temporal (15 min a 24 h) |
| `vwc_rolling_mean_4h/24h` | % VWC | Media móvil causal de 4 h y 24 h | Tendencia de base hídrica |
| `vwc_rolling_std_4h` | % VWC | Desviación estándar móvil causal 4 h | Volatilidad reciente (detección de eventos de riego/lluvia) |
| `vwc_rate_1h/6h` | % VWC | Tasa de cambio en 1 h y 6 h | Velocidad de secado o infiltración |
| `target_vwc_1h/6h/12h/24h` | % VWC | Humedad real futura a $+1, +6, +12, +24$ horas | Objetivos supervisados para Modelo 2 |
""".format(train=len(train_df), val=len(val_df), test=len(test_df))

    with open(os.path.join(PROCESSED_DIR, "data_dictionary.md"), "w", encoding="utf-8") as f:
        f.write(dict_md)

    print("Preprocessing complete:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
