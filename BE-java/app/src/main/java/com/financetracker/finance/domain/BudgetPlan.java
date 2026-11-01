package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** A suggested or accepted monthly plan (BudgetPlanFS); lines are stored as JSON. */
@Entity
@Table(name = "fin_budget_plans")
public class BudgetPlan extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(name = "period_year", nullable = false)
    public int year;

    @Column(name = "period_month", nullable = false)
    public int month;

    @Column(nullable = false, length = 32)
    public String planType = "";

    /** suggested | accepted | superseded | dismissed */
    @Column(nullable = false, length = 16)
    public String status = "suggested";

    @Column(nullable = false, length = 32)
    public String reason = "manual";

    @Column(nullable = false, length = 3)
    public String currency = "USD";

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal incomeTotal = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal commitmentsTotal = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal available = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal needsTotal = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal wantsTotal = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal savingsAmount = BigDecimal.ZERO;

    /** [{group_id, group_name, bucket, amount, average_spend, current_forecast, basis}] with string amounts. */
    @Convert(converter = JsonColumnConverters.MapList.class)
    @Column(name = "lines_json", nullable = false, length = 100000)
    public List<Map<String, Object>> lines = new ArrayList<>();

    @Convert(converter = JsonColumnConverters.StringList.class)
    @Column(name = "warnings_json", nullable = false, length = 20000)
    public List<String> warnings = new ArrayList<>();

    public Instant acceptedAt;
    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
