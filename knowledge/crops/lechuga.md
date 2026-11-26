# Perfil Agronómico: Lechuga (*Lactuca sativa*)

## 1. Identificación del Cultivo
- **Nombre común:** Lechuga
- **Nombre científico:** *Lactuca sativa* L.
- **Familia botánica:** Asteraceae
- **ID de perfil en AgroRiego AI:** `lechuga`

## 2. Descripción y Características Agronómicas
Cultivo hortícola de hoja con ciclo vegetativo corto (65–85 días) y sistema radicular sumamente superficial, concentrando más del 80 % de sus raíces activas en los primeros 0.15–0.35 m del perfil del suelo (Allen et al., 1998; Brouwer & Heibloem, 1986). Debido a su escaso volumen de exploración edáfica y elevado contenido de agua foliar (> 94 %), responde de forma inmediata tanto al déficit como al exceso hídrico.

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
Referencias basadas en FAO N.º 56 (Allen et al., 1998, Tabla 11 y Tabla 12):

| Etapa Fenológica | Duración Referencial (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=4.0$ mm/d) |
|---|---|---|---|---|
| Inicial (`inicial`) | 20 | 0.15 | 0.70 | 2.80 mm/día |
| Desarrollo (`desarrollo`) | 30 | 0.25 | 0.85 | 3.40 mm/día |
| Media temporada (`medio`) | 15 | 0.35 | 1.00 | 4.00 mm/día |
| Final / Cosecha (`final`) | 10 | 0.35 | 0.95 | 3.80 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo franco-arenoso con $\theta_{CC}$ = **30.0 % VWC** y $\theta_{PMP}$ = **13.0 % VWC**.
- **Fracción de agotamiento permisible ($p$):** **0.30** (cultivo altamente sensible al agotamiento hídrico, Allen et al., 1998, Tabla 22). Umbral óptimo inferior $\theta_{\min} = 30.0 - 0.30 \times (30.0 - 13.0) = 24.9\%$ VWC.
- **Saturación / Exceso:** Saturación = 45.0 % VWC; umbral de alerta por exceso > **36.0 % VWC**.
- **Humedad relativa ambiental (% HR):** Rango recomendado **65 % – 80 %**.
- **Características del suelo:** Textura franca o franco-arenosa rica en materia orgánica, pH óptimo 6.0–7.0, buen drenaje superficial.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima diurna: **15–21 °C**. Temperaturas nocturnas elevadas (> 24 °C) inducen floración prematura (*espigamiento / bolting*) y sabor amargo en hojas.

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia:** Riegos frecuentes de bajo volumen (goteo o microaspersión controlada) manteniendo la zona radicular superior entre **24.9 % y 29.8 % VWC**.
- **Sensibilidad a sequía:** Déficits breves provocan cierre estomático, reducción drástica de biomasa y **quemadura marginal (*tipburn*)** por interrupción del flujo xilemático de calcio hacia hojas jóvenes.
- **Sensibilidad a exceso:** Encharcamiento > 36 % VWC favorece podredumbre basal por *Sclerotinia sclerotiorum* y *Botrytis cinerea*.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC` a profundidad somera (10–20 cm), temperatura del suelo, temperatura ambiental, `% HR` y $ET_c$.
- **Criterios de recomendación:** Activar alerta preventiva si el pronóstico de 6 h cae < 25.5 % VWC y recomendar pulso corto de riego (< 15 min, histéresis `+2.5 %`, cooldown `60 min`) al cruzar `24.9 % VWC`.

## 8. Limitaciones de la Información
La calibración específica para sustratos orgánicos muy ligeros (turba/fibra de coco en hidroponía) difiere de los suelos minerales agrícolas sobre los cuales se calibró el sensor capacitivo del dataset de referencia.

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- Brouwer, C., & Heibloem, M. (1986). *Irrigation water management: Training manual No. 3 — Irrigation water needs*. FAO. https://www.fao.org/4/S2022E/s2022e00.htm
