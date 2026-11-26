# Perfil Agronómico: Tomate (*Solanum lycopersicum*)

## 1. Identificación del Cultivo
- **Nombre común:** Tomate
- **Nombre científico:** *Solanum lycopersicum* L.
- **Familia botánica:** Solanaceae
- **ID de perfil en AgroRiego AI:** `tomate`

## 2. Descripción y Características Agronómicas
Hortaliza de fruto de ciclo semi-perenne manejada comercialmente como cultivo anual (90–145 días según variedad determinada o indeterminada). En Costa Rica constituye una de las principales hortalizas hortícolas registradas en la Encuesta Nacional Agropecuaria (INEC, 2025). Presenta sistema radicular pivotante con densa ramificación lateral concentrada en los primeros 0.30–0.60 m y capacidad de exploración hasta 1.0–1.5 m en suelos profundos (Allen et al., 1998).

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
De acuerdo con el Manual FAO N.º 56 (Allen et al., 1998, Tabla 11 y Tabla 12):

| Etapa Fenológica | Duración Referencial (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=4.5$ mm/d) |
|---|---|---|---|---|
| Inicial (`inicial`) | 30 | 0.30 | 0.60 | 2.70 mm/día |
| Desarrollo (`desarrollo`) | 40 | 0.65 | 0.88 | 3.96 mm/día |
| Media temporada (`medio`) | 45 | 1.00 | 1.15 | 5.18 mm/día |
| Final / Maduración (`final`) | 30 | 1.00 | 0.80 | 3.60 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
Es fundamental distinguir las variables físicas monitoreadas por el sistema:
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Para suelo franco de referencia, Capacidad de Campo ($\theta_{CC}$) = **31.0 % VWC** y Punto de Marchitez Permanente ($\theta_{PMP}$) = **14.0 % VWC** (agua disponible total $TAW = 17.0\%$ VWC).
- **Fracción de agotamiento permisible ($p$):** **0.40** (Allen et al., 1998, Tabla 22). Por tanto, el umbral óptimo inferior antes de iniciar estrés es $\theta_{\min} = 31.0 - 0.40 \times (31.0 - 14.0) = 24.2\%$ VWC.
- **Saturación / Exceso hídrico:** Saturación = 46.0 % VWC; umbral de alerta por exceso > **37.0 % VWC**.
- **Humedad relativa ambiental (% HR):** Rango óptimo atmosférico de **60 % a 75 %** (no confundir con la humedad volumétrica del suelo).
- **Características del suelo:** Franco a franco-arenoso profundo, bien drenado, pH 6.0–6.8, conductividad eléctrica < 2.5 dS/m.

## 5. Condiciones Ambientales Importantes
- Temperatura diurna óptima: **20–27 °C**; temperaturas > 32 °C reducen viabilidad del polen y elevan la evapotranspiración de referencia ($ET_0$).
- Humedad relativa sostenida > 85 % favorece enfermedades foliares (*Phytophthora infestans*, *Alternaria solani*).

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia recomendada:** Riego por goteo de alta precisión con pulsos cortos y frecuentes en floración y llenado de fruto, manteniendo la humedad dentro de la banda **24.2 % – 30.5 % VWC**.
- **Sensibilidad a sequía:** Muy alta durante floración y cuajado de fruto. Fluctuaciones bruscas causan **pudrición apical (*blossom-end rot*)** por deficiencia localizada de calcio.
- **Sensibilidad a exceso:** Suelos saturados > 37 % VWC por más de 24 h provocan hipoxia radicular, caída de flores y agrietamiento de frutos maduros tras lluvias o riegos excesivos.

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC` (calibrado de ADC o sensor capacitivo), temperatura del suelo, temperatura ambiental, `% HR` ambiental, $ET_c$ estimada e historial de activación de bomba.
- **Criterios de recomendación en AgroRiego AI:** Activar recomendación cuando `% VWC actual` o `% VWC predicha (1h/6h)` descienda por debajo de `24.2 % VWC` (o `20.5 % VWC` crítico), aplicando banda de histéresis de `+3.5 %` (`27.7 %` parada), cooldown mínimo de `90 min` y duración máxima de `25 min`.

## 8. Limitaciones de la Información
El dataset real primario (*EcoIrrigate*, Saha et al., 2026) no etiqueta explícitamente cultivos específicos de tomate en su archivo unificado; por ello, el modelo de ML predice la dinámica física de humedad del suelo y el motor agronómico aplica los parámetros FAO-56 específicos del tomate sobre dicha predicción. El dataset italiano Adamo et al. (2026, DOI `10.17632/c837v6p8ph.2`) sí incluye sectores de tomate en campo abierto y maceta como referencia bibliográfica complementaria.

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). Food and Agriculture Organization of the United Nations. https://www.fao.org/4/X0490E/X0490E00.htm
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. Instituto Nacional de Estadística y Censos. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
- INTA Costa Rica. (2019). *Manual técnico del cultivo de tomate bajo ambiente protegido*. Instituto Nacional de Innovación y Transferencia en Tecnología Agropecuaria.
