package com.financetracker.shared.locale;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.financetracker.shared.config.AppProperties;

import tools.jackson.databind.json.JsonMapper;

/**
 * Port of api/currency.py. Rates are "value of 1 unit in USD" floats, like settings.EXCHANGE_RATES;
 * arithmetic follows Python's Decimal defaults (28 significant digits, ROUND_HALF_EVEN).
 */
@Component
public class ExchangeRates {

    private static final MathContext PY_DECIMAL = new MathContext(28, RoundingMode.HALF_EVEN);

    private final Map<String, Double> rates;
    private final String asOf;

    public ExchangeRates(AppProperties props) {
        Map<String, Double> r = new LinkedHashMap<>();
        r.put("USD", 1.0);
        r.put("LBP", 1.0 / 89500);
        r.put("SAR", 1.0 / 3.75);
        props.getExchangeRates().forEach((k, v) -> r.put(k.toUpperCase(), v.doubleValue()));
        String json = props.getExchangeRatesJson();
        if (json != null && !json.isBlank()) {
            Map<?, ?> parsed = JsonMapper.builder().build().readValue(json, Map.class);
            parsed.forEach((k, v) -> {
                try {
                    r.put(String.valueOf(k).toUpperCase(), Double.parseDouble(String.valueOf(v)));
                } catch (NumberFormatException ignored) {
                    // same as Django: unparseable rates are skipped
                }
            });
        }
        r.put("USD", r.getOrDefault("USD", 1.0));
        this.rates = Map.copyOf(r);
        this.asOf = props.getExchangeRatesAsOf();
    }

    /** get_exchange_rates(): code -> float, USD first. */
    public Map<String, Double> rates() {
        Map<String, Double> out = new LinkedHashMap<>();
        out.put("USD", rates.get("USD"));
        rates.forEach((k, v) -> {
            if (!"USD".equals(k)) {
                out.put(k, v);
            }
        });
        return out;
    }

    public String asOf() {
        return asOf;
    }

    /** convert_amount(amount, from, to) quantized to 0.01. */
    public BigDecimal convert(BigDecimal amount, String fromCurrency, String toCurrency) {
        BigDecimal amt = amount == null ? BigDecimal.ZERO : amount;
        String src = LocaleDefaults.normalizeCurrency(fromCurrency == null || fromCurrency.isEmpty() ? "USD" : fromCurrency);
        String dst = LocaleDefaults.normalizeCurrency(toCurrency == null || toCurrency.isEmpty() ? "USD" : toCurrency);
        if (src.equals(dst)) {
            return amt.setScale(2, RoundingMode.HALF_EVEN);
        }
        BigDecimal srcRate = rate(src);
        BigDecimal dstRate = rate(dst);
        if (srcRate.signum() <= 0 || dstRate.signum() <= 0) {
            return amt.setScale(2, RoundingMode.HALF_EVEN);
        }
        BigDecimal usd = amt.multiply(srcRate, PY_DECIMAL);
        return usd.divide(dstRate, PY_DECIMAL).setScale(2, RoundingMode.HALF_EVEN);
    }

    /** convert_if_needed: unchanged amount when no report currency is requested. */
    public BigDecimal convertIfNeeded(BigDecimal amount, String fromCurrency, String reportCurrency) {
        if (reportCurrency == null || reportCurrency.isEmpty()) {
            return amount == null ? BigDecimal.ZERO : amount;
        }
        return convert(amount, fromCurrency == null || fromCurrency.isEmpty() ? "USD" : fromCurrency, reportCurrency);
    }

    private BigDecimal rate(String code) {
        Double r = rates.get(code);
        if (r == null) {
            return "USD".equals(code) ? BigDecimal.ONE : BigDecimal.ZERO;
        }
        // Decimal(str(float)): shortest round-trip repr, same digits in Java and Python.
        return new BigDecimal(Double.toString(r));
    }
}
