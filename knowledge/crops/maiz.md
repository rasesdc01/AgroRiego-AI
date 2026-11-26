# Perfil Agronómico: Maíz (*Zea mays*)

## 1. Identificación del Cultivo
- **Nombre común:** Maíz
- **Nombre científico:** *Zea mays* L.
- **Familia botánica:** Poaceae
- **ID de perfil en AgroRiego AI:** `maiz`

## 2. Descripción y Características Agronómicas
Gramínea anual C4 de alto potencial fotosintético y cultivo básico prioritario en Costa Rica (INEC, 2025). Desarrolla un sistema radicular fibroso que alcanza entre 1.0 y 1.5 m en suelos profundos, permitiendo tolerar cierto agotamiento hídrico durante la fase vegetativa inicial pero exhibiendo vulnerabilidad crítica durante la emisión de estigmas y floración masculina (*tasseling/silking*).

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
Valores oficiales FAO N.º 56 (Allen et al., 1998, Tabla 12, p. 112):

| Etapa Fenológica | Duración (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=5.0$ mm/d) |
|---|---|---|---|---|
| Inicial (`inicial`) | 20 | 0.30 | 0.30 | 1.50 mm/día |
| Desarrollo (`desarrollo`) | 35 | 0.70 | 0.75 | 3.75 mm/día |
| Media temporada / Floración (`medio`) | 40 | 1.20 | 1.20 | 6.00 mm/día |
| Final / Secado de grano (`final`) | 30 | 1.20 | 0.50 | 2.50 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo franco de referencia con $\theta_{CC}$ = **32.0 % VWC** y $\theta_{PMP}$ = **15.0 % VWC**.
- **Fracción de agotamiento permisible ($p$):** **0.55** (Allen et al., 1998, Tabla 22). Umbral óptimo inferior $\theta_{\min} = 32.0 - 0.55 \times (32.0 - 15.0) = 22.65\%$ VWC (aprox. 22.6 % VWC).
- **Saturación / Exceso:** Saturación = 47.0 % VWC; alerta de exceso > **39.0 % VWC**.
- **Humedad relativa ambiental (% HR):** Rango óptimo **55 % – 75 %**.
- **Características del suelo:** Suelo franco a franco-limoso profundo, pH 5.8–7.0, buena aireación radicular.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima: **22–30 °C**. Olas de calor > 34 °C combinadas con déficit hídrico durante polinización deshidratan el polen y causan fallas de fecundación en la mazorca.

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia:** Riegos de lámina media espaciados en fase vegetativa y control estricto sin déficit entre emergencia de espiga y llenado lechoso del grano (`medio`). Reducción gradual en `final` para secado fisiológico.
- **Sensibilidad a sequía:** Pérdidas de rendimiento superiores al 50 % si el estrés (< 19.5 % VWC) coincide con las 2 semanas alrededor de floración.
- **Sensibilidad a exceso:** Encharcamiento prolongado en plántula (`inicial`) amarillea las hojas por lixiviación de nitrógeno y asfixia radicular.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC`, temperatura aire/suelo, `% HR`, $ET_c$ y etapa de desarrollo.
- **Criterios de recomendación:** Iniciar riego al bajar de `22.6 % VWC` (elevando prioridad si la etapa activa es `medio` / floración), histéresis `+4.0 %`, cooldown `120 min`, duración máx `30 min`.

## 8. Limitaciones de la Información
La profundidad efectiva real depende de la presencia de capas compactadas (pie de arado) que pueden limitar las raíces por debajo de 0.60 m.

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
