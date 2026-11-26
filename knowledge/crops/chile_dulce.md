# Perfil Agronómico: Chile Dulce (*Capsicum annuum*)

## 1. Identificación del Cultivo
- **Nombre común:** Chile dulce / Pimiento morrón
- **Nombre científico:** *Capsicum annuum* L.
- **Familia botánica:** Solanaceae
- **ID de perfil en AgroRiego AI:** `chile_dulce`

## 2. Descripción y Características Agronómicas
Solanácea hortícola de alto valor comercial cultivada en Costa Rica tanto a campo abierto como bajo ambiente protegido (MAG/INTA, 2020; INEC, 2025). Posee un sistema radicular relativamente compacto y superficial (0.25–0.80 m) con menor capacidad de extracción profunda que el tomate, lo que lo hace muy dependiente de humedad estable en los primeros 40 cm del suelo.

## 3. Etapas de Crecimiento y Coeficientes de Cultivo ($K_c$)
Valores basados en FAO N.º 56 (Allen et al., 1998, Tabla 12, p. 110 para *Sweet Peppers*):

| Etapa Fenológica | Duración (días) | Profundidad Radicular $Z_r$ (m) | Coeficiente $K_c$ | Demanda Relativa $ET_c$ ($ET_0=4.5$ mm/d) |
|---|---|---|---|---|
| Inicial (`inicial`) | 30 | 0.25 | 0.60 | 2.70 mm/día |
| Desarrollo (`desarrollo`) | 35 | 0.50 | 0.82 | 3.69 mm/día |
| Media temporada / Fructificación (`medio`) | 40 | 0.80 | 1.05 | 4.73 mm/día |
| Final / Cosecha continua (`final`) | 20 | 0.80 | 0.90 | 4.05 mm/día |

## 4. Necesidades Hídricas y Parámetros Edáficos
- **Humedad volumétrica del suelo ($\theta_v$, % VWC):** Suelo franco a franco-arenoso con $\theta_{CC}$ = **31.0 % VWC** y $\theta_{PMP}$ = **14.0 % VWC**.
- **Fracción de agotamiento permisible ($p$):** **0.30** (Allen et al., 1998, Tabla 22). Umbral óptimo inferior $\theta_{\min} = 31.0 - 0.30 \times (31.0 - 14.0) = 25.9\%$ VWC.
- **Saturación / Exceso hídrico:** Saturación = 46.0 % VWC; umbral de alerta por exceso > **35.5 % VWC**.
- **Humedad relativa ambiental (% HR):** Óptimo **60 % – 75 %**.
- **Características del suelo:** Textura media, alta aireación, pH 6.0–6.8, drenaje rápido.

## 5. Condiciones Ambientales Importantes
- Temperatura óptima: **20–28 °C**. Temperaturas > 32 °C con baja humedad relativa (< 50 % HR) causan caída masiva de botones florales y frutos recién cuajados.

## 6. Estrategia de Riego y Sensibilidad a Sequía / Exceso
- **Estrategia:** Riego por goteo de alta frecuencia con láminas bajas para sostener la humedad en la estrecha ventana **25.9 % – 30.5 % VWC**.
- **Sensibilidad a sequía:** Muy elevada; déficits breves (< 22.5 % VWC) ocasionan **aborto floral**, reducción de calibre del fruto y pudrición apical (*blossom-end rot*).
- **Sensibilidad a exceso:** Extremadamente susceptible al marchitamiento y muerte súbita por el oomiceto ***Phytophthora capsici*** cuando ocurre saturación prolongada alrededor del cuello de la planta (> 35.5 % VWC).

## 7. Variables Monitoreadas y Criterios de Recomendación
- **Variables:** `% VWC`, temperatura suelo/aire, `% HR` y $ET_c$.
- **Criterios de recomendación:** Activar recomendación al caer debajo de `25.9 % VWC` (banda de histéresis `+3.0 %`, cooldown `90 min`, máx `20 min`) y emitir alerta crítica de riesgo fitosanitario (*Phytophthora capsici*) si supera `35.5 % VWC`.

## 8. Limitaciones de la Información
En producción bajo invernadero o macrotúnel, la $ET_0$ interna suele ser un 20–30 % menor que a campo abierto debido a menor velocidad del viento y atenuación radiativa de la cubierta plástica.

## 9. Bibliografía
- Allen, R. G., Pereira, L. S., Raes, D., & Smith, M. (1998). *Crop evapotranspiration: Guidelines for computing crop water requirements* (FAO Irrigation and Drainage Paper No. 56). FAO. https://www.fao.org/4/X0490E/X0490E00.htm
- INEC Costa Rica. (2025). *Infografía de cultivos: Encuesta Nacional Agropecuaria (ENA) 2024*. https://admin.inec.cr/sites/default/files/2025-09/Infografia_Cultivos_ENA_2024.pdf
- MAG / INTA Costa Rica. (2020). *Manual de manejo agronómico del chile dulce*. Ministerio de Agricultura y Ganadería.
