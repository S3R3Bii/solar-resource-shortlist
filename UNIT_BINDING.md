# Returned unit binding before qualification or ranking

The 24 planned daily responses were captured successfully under the original protocol. A first schema inspection finds that POWER Daily API v2.10.1 returns `ALLSKY_SFC_SW_DWN` in **W m-2**, even for the requested SB community. Its JSON and CSV headers agree; the source is SYN1DEG and time standard UTC. The initial inspection also printed the first five daily values for W01; no annual aggregate, candidate forecast or ranking summary existed.

The original protocol requires dimensional confirmation and expressly disallows treating W/m2 as kWh/m2/day without a documented integration conversion. This note binds that permitted conversion before qualification and scoring. The official Daily API describes daily means, and the source-methodology page identifies daily-mean solar flux. NLR's solar-resource glossary distinguishes irradiance (power per area) from kWh (energy). For a 24-hour UTC day's mean irradiance:

`daily irradiation [kWh/m2/day] = daily mean [W/m2] * 24 [h/day] / 1000 [W/kW] = source * 3/125`.

This is exact unit arithmetic over the retained decimal token, not a photovoltaic conversion or a source-accuracy claim. Preserve native W/m2 and converted exact irradiation side by side. Never convert fill values into negative radiation or zeros. A constant positive factor preserves all resource ranks and shortlist decisions. An independent checker must recompute the factor from 24 hours and 1000 watts per kilowatt, including a fixture that 1000 W/m2 daily mean equals 24 kWh/m2/day.

No cohort gate, year, candidate, metric, missingness rule or selection criterion changes. The source unit differs from the anticipated community unit, and the post-capture/pre-score note is explicit. Do not call this an untouched source-unit preregistration. The documentation's native-resolution and source-edition qualifications remain applicable; no physical parcel output or field measurement is established.

Sources: https://power.larc.nasa.gov/docs/services/api/temporal/daily/ ; https://power.larc.nasa.gov/docs/methodology/data/sources_fluxes/ ; https://www.nlr.gov/grid/solar-resource/solar-glossary . Exact source-page captures and receipts are retained privately.
