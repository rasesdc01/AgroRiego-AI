# Perfil Agronómico: Café (*Coffea arabica*)

## 1. Identificación del Cultivo
- **Nombre común:** Café arábigo
- **Nombre científico:** *Coffea arabica* L.
- **Familia botánica:** Rubiaceae
- **ID de perfil en AgroRiego AI:** `cafe`

## 2. Descripción y Características Agronómicas
Arbusto perenne de importancia estratégica en Costa Rica, cultivado principalmente en suelos de origen volcánico (Andisoles) entre los 800 y 1,700 m s. n. m. (INEC, 2025; ICAFE, 2020). Presenta sistema radicular profundo (hasta 1.20–1.50 m) con mayor concentración de raíces absorbentes en los primeros 0.45 m.

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
Para cafetales adultos a pleno sol o sombra moderada sin cobertura herbácea densa (Allen et al., 1998, Tabla 12):

| Etapa Fenológica | Duración Referencial (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=4.2$ mm/d) |
|---|---|---|---|---|
| Inicial / Reposo y Prefloración (`inicial`) | 60 | 0.60 | 0.90 | 3.78 mm/día |
| Desarrollo / Floración y Cuaje (`desarrollo`) | 90 | 0.90 | 0.92 | 3.86 mm/día |
| Media temporada / Llenado de Grano (`medio`) | 120 | 1.20 | 0.95 | 3.99 mm/día |
| Final / Maduración y Cosecha (`final`) | 95 | 1.20 | 0.95 | 3.99 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo Andisol franco con alta retención hídrica: $\theta_{CC}$ = **36.0 % VWC**, $\theta_{PMP}$ = **18.0 % VWC**.
- **Fracción de agotamiento permisible ($p$):** **0.40** (Allen et al., 1998). Umbral óptimo inferior $\theta_{\min} = 36.0 - 0.40 \times (36.0 - 18.0) = 28.8\%$ VWC.
- **Saturación / Exceso:** Saturación = 52.0 % VWC; umbral de alerta por exceso > **43.0 % VWC**.
- **Humedad relativa ambiental (% HR):** Rango óptimo **70 % – 85 %**.
- **Características del suelo:** Andisol o franco-arcilloso profundo, rico en materia orgánica, pH ligeramente ácido **5.2–6.2** y excelente drenaje interno.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima: **18–24 °C**. Temperaturas sostenidas > 28 °C aceleran la maduración del fruto reduciendo la calidad de taza.

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia:** Riego localizado por goteo o microaspersión en época seca, particularmente crítico durante el **llenado de grano** (para evitar granos vanos o pequeños). En fases previas a floración, un estrés hídrico leve y controlado sincroniza la antesis floral tras el primer riego/lluvia.
- **Sensibilidad a sequía:** Déficits severos (< 24.0 % VWC) durante expansión del fruto generan abscisión de frutos y reducción de peso seco del grano.
- **Sensibilidad a exceso:** Encharcamientos prolongados (> 43 % VWC) favorecen asfixia radicular y patógenos vasculares.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC` radicular, temperatura ambiental y del suelo, `% HR` y $ET_c$.
- **Criterios de recomendación:** Recomendar riego si `% VWC` o predicción 12h/24h cae bajo `28.8 % VWC` en etapa de desarrollo/llenado (`medio`), con histéresis `+4.0 %`, cooldown `180 min` y máximo `35 min` de pulso.

## 8. Limitaciones de la Información
Los coeficientes $K_c$ varían según el porcentaje de sombra arbórea del cafetal (sistemas agroforestales reducen la radiación incidente y el $ET_c$ del estrato cafetero).

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- ICAFE Costa Rica. (2020). *Guía técnica para el cultivo del café*. Instituto del Café de Costa Rica.
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
