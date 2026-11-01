package com.financetracker.notifications.email;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Properties;

import jakarta.mail.internet.MimeMessage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

import com.financetracker.shared.config.AppProperties;

/**
 * Port of api/email_delivery.send_branded_email: multipart (plain + HTML). Uses SMTP when
 * EMAIL_HOST is set; otherwise prints the message to the log like Django's console backend.
 */
@Component
public class EmailDelivery {

    private static final Logger log = LoggerFactory.getLogger(EmailDelivery.class);

    private final AppProperties props;
    private final EmailRenderer renderer;
    private final JavaMailSenderImpl smtp;

    public EmailDelivery(AppProperties props, EmailRenderer renderer) {
        this.props = props;
        this.renderer = renderer;
        this.smtp = buildSender(props.getEmail());
    }

    public boolean send(BrandedEmail content, List<String> to) {
        return send(content, to, false);
    }

    /** Automatic notice (alert, reminder, plan suggestion, nudge): logged only when notifications are off. */
    public boolean sendNotification(BrandedEmail content, List<String> to) {
        return send(content, to, !props.getEmail().isNotificationsEnabled());
    }

    private boolean send(BrandedEmail content, List<String> to, boolean logOnly) {
        List<String> recipients = to.stream().filter(e -> e != null && !e.strip().isEmpty()).map(String::strip).toList();
        if (recipients.isEmpty()) {
            return false;
        }
        String plain = renderer.plainText(content);
        String html = renderer.html(content);
        if (smtp == null || logOnly) {
            log.info("Email (console backend)\nSubject: {}\nFrom: {}\nTo: {}\n\n{}", content.subject(),
                    props.getEmail().getFrom(), String.join(", ", recipients), plain);
            return true;
        }
        try {
            MimeMessage message = smtp.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
            helper.setSubject(content.subject());
            helper.setFrom(props.getEmail().getFrom());
            helper.setTo(recipients.toArray(String[]::new));
            helper.setText(plain, html);
            smtp.send(message);
            return true;
        } catch (Exception e) {
            log.warn("Failed to send email '{}' to {}: {}", content.subject(), recipients, e.getMessage());
            return false;
        }
    }

    private static JavaMailSenderImpl buildSender(AppProperties.Email cfg) {
        if (!cfg.isEnabled() || cfg.getHost() == null || cfg.getHost().isBlank()) {
            return null;
        }
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(cfg.getHost());
        sender.setPort(cfg.getPort());
        if (!cfg.getUsername().isEmpty()) {
            sender.setUsername(cfg.getUsername());
            sender.setPassword(cfg.getPassword());
        }
        Properties p = sender.getJavaMailProperties();
        p.put("mail.smtp.auth", String.valueOf(!cfg.getUsername().isEmpty()));
        p.put("mail.smtp.starttls.enable", String.valueOf(cfg.isUseTls()));
        p.put("mail.smtp.connectiontimeout", "10000");
        p.put("mail.smtp.timeout", "10000");
        return sender;
    }
}
