# Perfil Agronómico: Arroz (*Oryza sativa*) — Manejo Especializado de Inundación y Lámina de Agua

## 1. Identificación del Cultivo
- **Nombre común:** Arroz
- **Nombre científico:** *Oryza sativa* L.
- **Familia botánica:** Poaceae
- **ID de perfil en AgroRiego AI:** `arroz`
- **Régimen de manejo en AgroRiego AI:** `flood_paddy` (**Lógica diferenciada de inundación / lámina de agua**)

## 2. Descripción y Características Agronómicas
Cereal semiacuático que, bajo riego en melgas o terrazas niveladas, se cultiva mayoritariamente en condiciones de **saturación continua o lámina de agua superficial controlada (inundación somera)** durante las fases vegetativa y reproductiva (Allen et al., 1998; Brouwer et al., 1989). A diferencia de cultivos como tomate, lechuga o frijol —donde el encharcamiento causa asfixia radicular—, el arroz posee tejido aerénquima que transporta oxígeno desde el follaje hacia las raíces sumergidas.

## 3. Etapas de Crecimiento, Coeficientes $K_c$ y Lámina Objetivo
Según FAO N.º 56 (Tabla 12, p. 112) y FAO Training Manual No. 4 (Brouwer et al., 1989):

| Etapa Fenológica | Duración (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Lámina Superficial Objetivo (`water_lamina_mm`) |
|---|---|---|---|---|
| Inicial / Establecimiento (`inicial`) | 30 | 0.20 | 1.05 | **10 – 50 mm** (objetivo 30 mm) |
| Desarrollo / Macollamiento (`desarrollo`) | 30 | 0.35 | 1.12 | **25 – 80 mm** (objetivo 50 mm) |
| Media temporada / Floración y Llenado (`medio`) | 60 | 0.50 | 1.20 | **40 – 100 mm** (objetivo 70 mm) |
| Final / Maduración y Drenaje (`final`) | 30 | 0.50 | 0.75 | **0 – 15 mm (Drenaje pre-cosecha)** |

## 4. Necesidades Hídricas y Diferenciación de Variables
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo arcilloso/franco-arcilloso de baja conductividad hidráulica saturada: $\theta_{sat}$ = **50.0 % VWC**, $\theta_{CC}$ = **40.0 % VWC**, $\theta_{PMP}$ = **21.0 % VWC**.
- **Lámina de agua superficial (`water_lamina_mm`):** Variable exclusiva del perfil `arroz` medida en **milímetros (mm)** sobre la superficie del suelo. Mientras exista lámina > 0 mm, el suelo permanece en saturación (42–50 % VWC).
- **Fracción de agotamiento ($p$):** **0.20** para régimen no inundado o de humedecimiento y secado alternado (AWD), donde el umbral de estrés crítico ocurre por debajo de **36.0 % VWC**.
- **Humedad relativa ambiental (% HR):** Óptimo **70 % – 88 %**.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima: **24–32 °C**. Bajas temperaturas (< 18 °C) durante microsporogénesis inducen esterilidad espiguillar; en sistemas inundados la lámina actúa además como amortiguador térmico nocturno.

## 6. Estrategia de Riego Especializada (Distinta a Cultivos de Secano/Goteo)
El motor agronómico de AgroRiego AI **NO aplica la lógica estándar de capacidad de campo de tomate/lechuga** al arroz:
1. En etapas `inicial`, `desarrollo` y `medio`, el sistema evalúa **tanto la lámina superficial (`water_lamina_mm`) como la saturación del suelo (`>= 42.0 % VWC`)**.
2. Si `water_lamina_mm < min_water_lamina_mm` de la etapa o `soil_moisture_pct < 42.0 %`, se genera recomendación de **reposición de lámina hasta alcanzar el objetivo** (evitando rebalses por encima de `max_water_lamina_mm`).
3. En etapa **`final` (maduración pre-cosecha)**, el sistema activa la **regla de drenaje (`drainage_required: true`)**, bloqueando el llenado de agua aunque la lámina baje a 0 mm, siempre que la humedad del suelo supere `28 % VWC`, para permitir maduración uniforme y entrada de cosechadora.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `water_lamina_mm` (nivel de lámina), `% VWC` (saturación), temperatura del suelo/aire, `% HR` y etapa fenológica activa.
- **Criterios:** Nunca activar alerta de "exceso hídrico por saturación" mientras la lámina esté dentro de `max_water_lamina_mm` en etapas vegetativas/reproductivas; sí alertar desbordamiento si `water_lamina_mm > max_water_lamina_mm` o estrés severo si el suelo pierde saturación (< 36 % VWC) antes de la etapa final.

## 8. Limitaciones de la Información
Los parámetros corresponden a arroz bajo inundación controlada o manejo de humedecimiento y secado alternado (AWD); las variedades de arroz de secano estricto requieren umbrales aeróbicos distintos similares a cereales de secano.

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- Brouwer, C., Prins, K., & Heibloem, M. (1989). *Irrigation water management: Training manual No. 4 — Irrigation scheduling*. FAO. https://www.fao.org/4/S2022E/s2022e00.htm
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
