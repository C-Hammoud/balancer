package com.financetracker.notifications.email;

import java.util.ArrayList;
import java.util.List;

/** Port of api/email_template.BrandedEmail. */
public final class BrandedEmail {

    public record Cta(String label, String url) {
    }

    public record Row(String label, String value) {
    }

    final String subject;
    final String preheader;
    final String headline;
    final List<String> paragraphs = new ArrayList<>();
    final List<String> bullets = new ArrayList<>();
    final List<Row> detailRows = new ArrayList<>();
    Cta cta;
    Cta secondaryCta;
    String secondaryNote = "";
    String footerReason = "";

    public BrandedEmail(String subject, String preheader, String headline) {
        this.subject = subject;
        this.preheader = preheader;
        this.headline = headline;
    }

    public BrandedEmail paragraph(String p) {
        paragraphs.add(p);
        return this;
    }

    public BrandedEmail paragraphs(List<String> ps) {
        paragraphs.addAll(ps);
        return this;
    }

    public BrandedEmail row(String label, String value) {
        detailRows.add(new Row(label, value));
        return this;
    }

    public BrandedEmail cta(String label, String url) {
        this.cta = new Cta(label, url);
        return this;
    }

    public BrandedEmail secondaryCta(String label, String url) {
        this.secondaryCta = new Cta(label, url);
        return this;
    }

    public BrandedEmail secondaryNote(String note) {
        this.secondaryNote = note;
        return this;
    }

    public BrandedEmail footerReason(String reason) {
        this.footerReason = reason;
        return this;
    }

    public String subject() {
        return subject;
    }
}
