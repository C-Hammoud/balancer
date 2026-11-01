package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** One installment of a commitment (CommitmentScheduleLineFS). */
@Entity
@Table(name = "fin_schedule_lines", indexes = @Index(name = "ix_fin_schedule_commitment", columnList = "commitment_id"))
public class ScheduleLine extends StoredEntity {

    public static final String OUTSTANDING = "outstanding";
    public static final String PAID = "paid";

    @Column(nullable = false, length = 64)
    public String commitmentId = "";

    public LocalDate dueDate;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal amount = BigDecimal.ZERO;

    @Column(nullable = false, length = 20)
    public String status = OUTSTANDING;

    @Column(name = "seq_no", nullable = false)
    public int sequence;

    public LocalDate paidDate;

    @Column(nullable = false)
    public boolean reminderSent;
}
