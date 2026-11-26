# Perfil Agronómico: Frijol (*Phaseolus vulgaris*)

## 1. Identificación del Cultivo
- **Nombre común:** Frijol común
- **Nombre científico:** *Phaseolus vulgaris* L.
- **Familia botánica:** Fabaceae
- **ID de perfil en AgroRiego AI:** `frijol`

## 2. Descripción y Características Agronómicas
Leguminosa de ciclo corto (85–100 días) fundamental en la seguridad alimentaria costarricense (INEC, 2025; INTA, 2018). Posee sistema radicular fasciculado de profundidad moderada (0.50–0.70 m) en simbiosis con bacterias fijadoras de nitrógeno (*Rhizobium*), simbiosis altamente sensible a condiciones de anoxia del suelo.

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
De acuerdo con FAO N.º 56 (Allen et al., 1998, Tabla 12, p. 111 para *Beans, dry*):

| Etapa Fenológica | Duración (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=4.4$ mm/d) |
|---|---|---|---|---|
| Inicial (`inicial`) | 15 | 0.25 | 0.40 | 1.76 mm/día |
| Desarrollo (`desarrollo`) | 25 | 0.45 | 0.78 | 3.43 mm/día |
| Media temporada / Floración y Vainas (`medio`) | 35 | 0.70 | 1.15 | 5.06 mm/día |
| Final / Maduración (`final`) | 20 | 0.70 | 0.35 | 1.54 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo franco bien drenado con $\theta_{CC}$ = **29.0 % VWC** y $\theta_{PMP}$ = **13.0 % VWC**.
- **Fracción de agotamiento permisible ($p$):** **0.45** (Allen et al., 1998, Tabla 22). Umbral óptimo inferior $\theta_{\min} = 29.0 - 0.45 \times (29.0 - 13.0) = 21.8\%$ VWC.
- **Saturación / Exceso hídrico:** Saturación = 45.0 % VWC; umbral de alerta estricto por exceso > **33.5 % VWC** (más estricto que otros cultivos debido a su extrema sensibilidad a pudriciones radiculares).
- **Humedad relativa ambiental (% HR):** Óptimo **60 % – 75 %**.
- **Características del suelo:** Franco o franco-arenoso suelto, excelente drenaje interno y superficial, pH 6.0–6.8.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima: **18–26 °C**. Temperaturas > 30 °C durante floración provocan aborto floral severo.

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia:** Riego ligero y controlado por goteo para mantener entre **21.8 % y 28.5 % VWC**, evitando saturar la rizosfera y reduciendo el aporte al mínimo en maduración de vainas (`final`).
- **Sensibilidad a sequía:** Alta durante floración e inicio de formación de vainas, reduciendo número de vainas por planta.
- **Sensibilidad a exceso:** **Crítica**. Excesos hídricos > 33.5 % VWC durante > 12–24 h favorecen *Fusarium*, *Rhizoctonia solani*, *Pythium* y marchitez bacteriana, además de detener la fijación biológica de nitrógeno.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC`, temperatura suelo/aire, `% HR` y duración de eventos húmedos.
- **Criterios de recomendación:** Recomendar riego si `% VWC` < `21.8 %` (histéresis `+3.5 %`, cooldown `120 min`, máx `20 min`) y **bloquear inmediatamente el riego + emitir alerta de exceso hídrico** si `% VWC` > `33.5 %`.

## 8. Limitaciones de la Información
Las variedades arbustivas determinantes de Costa Rica presentan ciclos más cortos (~80 días) que las variedades de guía o enrame (~100–110 días).

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
- INTA Costa Rica. (2018). *Guía técnica para el cultivo de frijol común en Costa Rica*. Instituto Nacional de Innovación y Transferencia en Tecnología Agropecuaria.
