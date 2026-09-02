**5M Setup Engine Architecture & Design**

**Core Purpose**
Synthesizes higher-timeframe state (`1H Bias`, `15M Regime`, `15M Direction`) with local 5M price structure and momentum to flag high-probability trade triggers. It outputs setup states (`LONG_SETUP`, `SHORT_SETUP`, or `NONE`) without executing orders or calculating risk parameters.

**Input Contracts**

* **Higher-Timeframe State:** Consumes `bias_1h`, `regime_15m`, and `direction_15m` safely aligned or resampled to the 5M timeline.
* **5M Local Features:** Consumes 5M structural data from indicators (e.g., confirmed swing points, EMA boundaries, ATR, local price-to-EMA positioning).

**Testable Setup Hypotheses (V1 Scenarios)**

* **Trend Pullback Continuation:**
* *Conditions:* 1H Bias and 15M Direction match, 15M Regime is `TRENDING_EXPANSION`, and 5M price pulls back into a dynamic value zone (e.g., testing the EMA 9 / EMA 21 channel) before resuming structural momentum.


* **Compression Boundary Rejection:**
* *Conditions:* 15M Regime is `RANGING_COMPRESSION`, and 5M price interacts with a confirmed structural swing boundary with localized volatility contraction before printing a directional rejection candle.



**Design Rules & Guardrails**

* **Anti-Bloat Rule:** Restrict inputs strictly to structural moving averages, ATR, and swing coordinates—no auxiliary oscillators (RSI, MACD, Stochastic) to preserve mathematical transparency and prevent curve-fitting.
* **Hierarchical Veto Power:** Lower-timeframe setups inherit higher-timeframe constraints; a 5M long trigger is automatically blocked if the 1H macro bias is strictly `BEARISH`.

**Output Specification**

* Returns a pandas Series containing explicit setup classifications (`LONG_SETUP`, `SHORT_SETUP`, or `NONE`) for each evaluable 5M bar, ready for consumption by the 1M entry engine.