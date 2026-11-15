package com.financetracker.finance.application;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.encryption.InvalidPasswordException;
import org.apache.pdfbox.text.PDFTextStripper;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.json.JsonMapper;

/**
 * Port of budgeting/statement_formats.py: e-statements exported as JSON or PDF, turned into the
 * same rows as a CSV import (a date/description/amount header, then signed amounts; negative =
 * money out). The rules and messages match the Django version; see that module for the details.
 */
public final class StatementFormats {

    public static final List<String> HEADER = List.of("date", "description", "amount");

    /** Rows plus how many transactions had to assume their direction. */
    public record Parsed(List<List<String>> rows, int uncertain) {
    }

    /** The PDF is encrypted: code is password_required or password_incorrect. */
    public static class PasswordError extends StatementImporter.ImportError {
        private final String code;

        public PasswordError(String message, String code) {
            super(message);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    private StatementFormats() {
    }

    // ------------------------------------------------------------------------------------ JSON

    private static final JsonMapper JSON = JsonMapper.builder()
            .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
            .build();

    private static Set<String> with(Set<String> base, String... more) {
        Set<String> s = new HashSet<>(base);
        s.addAll(List.of(more));
        return s;
    }

    static final Set<String> DATE_KEYS = with(StatementImporter.HEADER_ALIASES.get("date"),
            "transaction date", "booking date", "value date", "date time", "datetime", "timestamp",
            "created at", "posted at", "posted date", "transaction time", "booking date time", "value date time");
    static final Set<String> DESCRIPTION_KEYS = with(StatementImporter.HEADER_ALIASES.get("description"),
            "transaction information", "remittance information unstructured", "remittance information",
            "merchant", "merchant name", "counterparty", "counterparty name", "beneficiary", "title", "label",
            "reference", "note", "notes", "purpose", "statement description");
    static final Set<String> AMOUNT_KEYS = with(StatementImporter.HEADER_ALIASES.get("amount"),
            "transaction amount", "instructed amount");
    static final Set<String> DEBIT_KEYS = with(StatementImporter.HEADER_ALIASES.get("debit"),
            "debit amount", "amount debit", "dr");
    static final Set<String> CREDIT_KEYS = with(StatementImporter.HEADER_ALIASES.get("credit"),
            "credit amount", "amount credit", "cr");
    static final Set<String> DIRECTION_KEYS = Set.of(
            "credit debit indicator", "debit credit indicator", "type", "direction", "transaction type",
            "dr cr", "cr dr", "indicator", "debit credit", "credit debit", "sign");
    static final Set<String> OUT_WORDS = Set.of("debit", "dr", "out", "expense", "withdrawal", "payment",
            "outgoing", "purchase", "fee");
    static final Set<String> IN_WORDS = Set.of("credit", "cr", "in", "income", "deposit", "incoming", "refund",
            "salary");

    /** bookingDate / Booking_Date / booking-date -> "booking date". */
    static String normKey(String key) {
        String spaced = String.valueOf(key).replaceAll("(?<=[a-z0-9])(?=[A-Z])", " ");
        return String.join(" ", spaced.toLowerCase(Locale.ROOT).split("[\\s_.\\-]+")).strip();
    }

    /** {"amount": {"value": 1}} -> {"amount value": 1, "value": 1}; the first bare key wins. */
    static Map<String, Object> flatten(Map<?, ?> obj, String prefix) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<?, ?> e : obj.entrySet()) {
            String name = normKey(String.valueOf(e.getKey()));
            String full = (prefix + " " + name).strip();
            Object value = e.getValue();
            if (value instanceof Map<?, ?> nested) {
                flatten(nested, full).forEach(out::putIfAbsent);
                flatten(nested, "").forEach(out::putIfAbsent);
            } else if (!(value instanceof List<?>)) {
                out.putIfAbsent(full, value);
                out.putIfAbsent(name, value);
            }
        }
        return out;
    }

    private static boolean blank(Object v) {
        return v == null || "".equals(v);
    }

    static Object pick(Map<String, Object> flat, Set<String> keys) {
        for (Map.Entry<String, Object> e : flat.entrySet()) {
            if (keys.contains(e.getKey()) && !blank(e.getValue())) {
                return e.getValue();
            }
        }
        return null;
    }

    private static Object nestedAmount(Map<?, ?> record) {
        for (Map.Entry<?, ?> e : record.entrySet()) {
            if (AMOUNT_KEYS.contains(normKey(String.valueOf(e.getKey()))) && e.getValue() instanceof Map<?, ?> inner) {
                Map<String, Object> keyed = new LinkedHashMap<>();
                inner.forEach((k, v) -> keyed.put(normKey(String.valueOf(k)), v));
                for (String k : List.of("amount", "value", "amt")) {
                    if (!blank(keyed.get(k))) {
                        return keyed.get(k);
                    }
                }
            }
        }
        return null;
    }

    private static boolean looksLikeTransaction(Object item) {
        if (!(item instanceof Map<?, ?> m)) {
            return false;
        }
        Set<String> keys = flatten(m, "").keySet();
        boolean hasAmount = keys.stream().anyMatch(k -> AMOUNT_KEYS.contains(k) || DEBIT_KEYS.contains(k)
                || CREDIT_KEYS.contains(k));
        return hasAmount && keys.stream().anyMatch(DATE_KEYS::contains);
    }

    private static void transactionLists(Object node, List<List<?>> found) {
        if (node instanceof List<?> list) {
            long hits = list.stream().filter(StatementFormats::looksLikeTransaction).count();
            if (!list.isEmpty() && hits * 2 >= list.size()) {
                found.add(list);
            }
            list.forEach(item -> transactionLists(item, found));
        } else if (node instanceof Map<?, ?> map) {
            map.values().forEach(v -> transactionLists(v, found));
        }
    }

    static String text(Object v) {
        return v instanceof BigDecimal d ? d.toPlainString() : String.valueOf(v);
    }

    private static String dateText(Object value) {
        if (value instanceof Number n && !(value instanceof Double) && !(value instanceof Float)) {
            long seconds = n.longValue();
            if (seconds > 100_000_000_000L) { // milliseconds
                seconds /= 1000;
            }
            return Instant.ofEpochSecond(seconds).atZone(ZoneOffset.UTC).toLocalDate().toString();
        }
        return text(value).strip();
    }

    private static int directionSign(Object value) {
        String[] words = text(value).toLowerCase(Locale.ROOT).split("[^a-z]+");
        for (String w : words) {
            if (OUT_WORDS.contains(w)) {
                return -1;
            }
        }
        for (String w : words) {
            if (IN_WORDS.contains(w)) {
                return 1;
            }
        }
        return 0;
    }

    public static List<List<String>> jsonRows(byte[] raw) {
        Object data;
        try {
            data = JSON.readValue(StatementImporter.decodeBytes(raw), Object.class);
        } catch (JacksonException | StatementImporter.ImportError e) {
            throw new StatementImporter.ImportError("This JSON file could not be read.");
        }
        List<List<?>> candidates = new ArrayList<>();
        transactionLists(data, candidates);
        if (candidates.isEmpty()) {
            throw new StatementImporter.ImportError(
                    "No transactions found in this JSON file (each needs a date and an amount).");
        }
        List<?> records = candidates.get(0);
        for (List<?> c : candidates) {
            if (c.size() > records.size()) {
                records = c;
            }
        }

        List<List<String>> rows = new ArrayList<>();
        rows.add(HEADER);
        for (Object item : records) {
            if (!(item instanceof Map<?, ?> record)) {
                continue;
            }
            Map<String, Object> flat = flatten(record, "");
            Object dateValue = pick(flat, DATE_KEYS);
            Object description = pick(flat, DESCRIPTION_KEYS);
            Object amount = nestedAmount(record);
            if (amount == null) {
                amount = pick(flat, AMOUNT_KEYS);
            }
            String amountText = "";
            if (amount != null) {
                amountText = text(amount);
                Object direction = pick(flat, DIRECTION_KEYS);
                BigDecimal value = null;
                try {
                    value = StatementImporter.parseAmount(amountText);
                } catch (IllegalArgumentException e) {
                    // left as written; the import reports the row
                }
                if (value != null && value.signum() > 0 && direction != null && directionSign(direction) < 0) {
                    amountText = value.negate().toPlainString();
                }
            } else {
                Object debit = pick(flat, DEBIT_KEYS);
                Object credit = pick(flat, CREDIT_KEYS);
                try {
                    if (!blank(credit) && StatementImporter.parseAmount(text(credit)).signum() != 0) {
                        amountText = StatementImporter.parseAmount(text(credit)).abs().toPlainString();
                    } else if (!blank(debit)) {
                        amountText = StatementImporter.parseAmount(text(debit)).abs().negate().toPlainString();
                    }
                } catch (IllegalArgumentException e) {
                    amountText = text(!blank(credit) ? credit : debit);
                }
            }
            rows.add(List.of(dateValue != null ? dateText(dateValue) : "",
                    description != null ? text(description).strip() : "", amountText));
        }
        return rows;
    }

    // ------------------------------------------------------------------------------------- PDF

    private static final String MONTH_NAMES = "jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec";
    static final Pattern DATE_RE = Pattern.compile(
            "^\\s*(\\d{4}-\\d{1,2}-\\d{1,2}"
                    + "|\\d{1,2}[/.\\-]\\d{1,2}[/.\\-]\\d{2,4}"
                    + "|\\d{1,2}[ \\-]?(?:" + MONTH_NAMES + ")[a-z]*[ \\-,]*\\d{2,4})(?![\\d/.\\-])",
            Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS);
    private static final Pattern MONTH_DATE_RE = Pattern.compile(
            "(\\d{1,2})[ \\-]?(" + MONTH_NAMES + ")[a-z]*[ \\-,]*(\\d{2,4})", Pattern.CASE_INSENSITIVE);
    /** Two decimals are required so reference and card numbers are not read as amounts. */
    static final Pattern AMOUNT_RE = Pattern.compile(
            "(?<![\\w.,'])(?<neg>-\\s?)?(?<open>\\()?"
                    + "(?<num>\\d{1,3}(?:[,.']\\d{3})+[.,]\\d{2}|\\d+[.,]\\d{2})"
                    + "(?<close>\\))?(?<trail>-)?(?:\\s?(?<mark>CR|DR|Cr|Dr|cr|dr)\\b)?(?![\\w.,]?\\d)",
            Pattern.UNICODE_CHARACTER_CLASS);
    private static final Map<String, Integer> MONTHS = Map.ofEntries(
            Map.entry("jan", 1), Map.entry("feb", 2), Map.entry("mar", 3), Map.entry("apr", 4), Map.entry("may", 5),
            Map.entry("jun", 6), Map.entry("jul", 7), Map.entry("aug", 8), Map.entry("sep", 9), Map.entry("oct", 10),
            Map.entry("nov", 11), Map.entry("dec", 12));
    static final List<String> BALANCE_WORDS = List.of(
            "opening balance", "closing balance", "balance brought forward", "balance carried forward",
            "brought forward", "carried forward", "previous balance", "balance b/f", "balance c/f",
            "starting balance", "ending balance", "beginning balance");
    static final List<String> OPENING_WORDS = List.of(
            "opening balance", "balance brought forward", "brought forward", "previous balance",
            "balance b/f", "starting balance", "beginning balance");
    static final Set<String> SKIP_WORDS = Set.of("total", "subtotal", "sub total");
    static final int MAX_CONTINUATION_LINES = 3;
    static final int CONTINUATION_MAX_CHARS = 40;
    private static final BigDecimal CENT = new BigDecimal("0.01");

    /** One amount token: signed value, whether the token itself said in or out, and its CR/DR marker. */
    record Amount(BigDecimal value, boolean explicit, String mark) {
    }

    private static final class Record {
        String date;
        final List<String> parts = new ArrayList<>();
        List<Amount> amounts = new ArrayList<>();
        String description;
        BigDecimal opening;
    }

    /** 03 Apr 2026 / 03-APR-26 -> 2026-04-03; other date formats are returned unchanged. */
    static String monthDateIso(String text) {
        Matcher m = MONTH_DATE_RE.matcher(text.strip());
        if (!m.matches()) {
            return text.strip();
        }
        int day = Integer.parseInt(m.group(1));
        int month = MONTHS.get(m.group(2).toLowerCase(Locale.ROOT).substring(0, 3));
        int year = Integer.parseInt(m.group(3));
        if (year < 100) {
            year += 2000;
        }
        return String.format("%04d-%02d-%02d", year, month, day);
    }

    private static Amount signed(Matcher m) {
        BigDecimal value = StatementImporter.parseAmount(m.group("num")).abs();
        String mark = m.group("mark") == null ? "" : m.group("mark").toUpperCase(Locale.ROOT);
        if (m.group("neg") != null || (m.group("open") != null && m.group("close") != null)
                || m.group("trail") != null || "DR".equals(mark)) {
            return new Amount(value.negate(), true, mark);
        }
        if ("CR".equals(mark)) {
            return new Amount(value, true, mark);
        }
        return new Amount(value, false, mark);
    }

    private static String stripChars(String s, String chars) {
        int start = 0;
        int end = s.length();
        while (start < end && chars.indexOf(s.charAt(start)) >= 0) {
            start++;
        }
        while (end > start && chars.indexOf(s.charAt(end - 1)) >= 0) {
            end--;
        }
        return s.substring(start, end);
    }

    /** Text before the first amount, and the amounts on one line. */
    private static Map.Entry<String, List<Amount>> splitAmounts(String text) {
        Matcher m = AMOUNT_RE.matcher(text);
        List<Amount> amounts = new ArrayList<>();
        int first = -1;
        while (m.find()) {
            if (first < 0) {
                first = m.start();
            }
            amounts.add(signed(m));
        }
        String head = first >= 0 ? text.substring(0, first) : text;
        return Map.entry(stripChars(head, " -|:\t"), amounts);
    }

    private static boolean containsAny(String text, List<String> words) {
        return words.stream().anyMatch(text::contains);
    }

    /** Group lines into transactions, plus opening balances found between them. */
    private static List<Record> records(List<String> lines) {
        List<Record> out = new ArrayList<>();
        Record record = null;
        int extra = 0;
        for (String line : lines) {
            String text = line.strip();
            if (text.isEmpty()) {
                continue;
            }
            Matcher date = DATE_RE.matcher(text);
            if (date.lookingAt()) {
                if (record != null) {
                    out.add(record);
                }
                String rest = text.substring(date.end());
                Matcher valueDate = DATE_RE.matcher(rest); // posting date followed by a value date
                if (valueDate.lookingAt()) {
                    rest = rest.substring(valueDate.end());
                }
                Map.Entry<String, List<Amount>> split = splitAmounts(rest);
                record = new Record();
                record.date = date.group(1);
                if (!split.getKey().isEmpty()) {
                    record.parts.add(split.getKey());
                }
                record.amounts = split.getValue();
                extra = 0;
                continue;
            }
            if (record != null && record.amounts.isEmpty() && extra < MAX_CONTINUATION_LINES) {
                Map.Entry<String, List<Amount>> split = splitAmounts(text);
                if (!split.getValue().isEmpty() || text.length() <= CONTINUATION_MAX_CHARS) {
                    if (!split.getKey().isEmpty()) {
                        record.parts.add(split.getKey());
                    }
                    record.amounts = split.getValue();
                    extra++;
                    continue;
                }
            }
            if (record != null) {
                out.add(record);
                record = null;
            }
            if (containsAny(text.toLowerCase(Locale.ROOT), OPENING_WORDS)) {
                List<Amount> amounts = splitAmounts(text).getValue();
                if (!amounts.isEmpty()) {
                    Record opening = new Record();
                    opening.opening = amounts.get(amounts.size() - 1).value();
                    out.add(opening);
                }
            }
        }
        if (record != null) {
            out.add(record);
        }
        return out;
    }

    /** True when each row's last amount moves by exactly one of the row's other amounts. */
    private static boolean hasRunningBalance(List<Record> records) {
        int pairs = 0;
        int hits = 0;
        BigDecimal previous = null;
        for (Record rec : records) {
            if (rec.amounts.size() < 2) {
                previous = null;
                continue;
            }
            BigDecimal last = rec.amounts.get(rec.amounts.size() - 1).value();
            if (previous != null) {
                pairs++;
                BigDecimal delta = last.subtract(previous).abs();
                if (delta.signum() != 0 && rec.amounts.subList(0, rec.amounts.size() - 1).stream()
                        .anyMatch(a -> a.value().abs().subtract(delta).abs().compareTo(CENT) < 0)) {
                    hits++;
                }
            }
            previous = last;
        }
        return pairs >= 2 && hits * 10 >= pairs * 6;
    }

    public static Parsed parsePdfLines(List<String> lines) {
        List<Record> records = new ArrayList<>();
        BigDecimal balance = null;
        for (Record item : records(lines)) {
            if (item.opening != null) {
                if (records.isEmpty()) {
                    balance = item.opening;
                }
                continue;
            }
            String description = String.join(" ", item.parts).strip();
            String lower = description.toLowerCase(Locale.ROOT);
            if (containsAny(lower, BALANCE_WORDS)) {
                if (records.isEmpty() && containsAny(lower, OPENING_WORDS) && !item.amounts.isEmpty()) {
                    balance = item.amounts.get(item.amounts.size() - 1).value();
                }
                continue;
            }
            if (description.isEmpty() || SKIP_WORDS.contains(lower)
                    || item.amounts.stream().allMatch(a -> a.value().signum() == 0)) {
                continue;
            }
            item.description = description;
            records.add(item);
        }
        if (records.isEmpty()) {
            throw new StatementImporter.ImportError(
                    "No transactions found in this PDF. Export the statement as CSV, Excel or JSON instead.");
        }

        boolean runningBalance = hasRunningBalance(records);
        Set<String> markers = new HashSet<>();
        records.forEach(r -> r.amounts.forEach(a -> {
            if (!a.mark().isEmpty()) {
                markers.add(a.mark());
            }
        }));
        // Only one side marked: cards print "CR" on credits, some banks print "DR" on debits.
        Integer unmarkedSign = markers.equals(Set.of("CR")) ? Integer.valueOf(-1)
                : markers.equals(Set.of("DR")) ? Integer.valueOf(1) : null;

        List<List<String>> rows = new ArrayList<>();
        rows.add(HEADER);
        int uncertain = 0;
        for (Record rec : records) {
            List<Amount> amounts = rec.amounts;
            BigDecimal value;
            boolean explicit;
            if (runningBalance && amounts.size() >= 2) {
                BigDecimal newBalance = amounts.get(amounts.size() - 1).value();
                Amount txn = amounts.subList(0, amounts.size() - 1).stream()
                        .filter(a -> a.value().signum() != 0).findFirst().orElse(amounts.get(0));
                value = txn.value();
                explicit = txn.explicit();
                if (!explicit && balance != null
                        && newBalance.subtract(balance).abs().subtract(value.abs()).abs().compareTo(CENT) < 0) {
                    value = newBalance.compareTo(balance) >= 0 ? value.abs() : value.abs().negate();
                    explicit = true;
                }
                balance = newBalance;
            } else {
                List<Amount> nonzero = amounts.stream().filter(a -> a.value().signum() != 0).toList();
                Amount txn = nonzero.get(nonzero.size() - 1);
                value = txn.value();
                explicit = txn.explicit();
            }
            if (!explicit) {
                if (unmarkedSign == null) {
                    uncertain++;
                }
                value = unmarkedSign != null && unmarkedSign > 0 ? value.abs() : value.abs().negate();
            }
            rows.add(List.of(monthDateIso(rec.date), rec.description, value.toPlainString()));
        }
        return new Parsed(rows, uncertain);
    }

    public static List<String> pdfTextLines(byte[] raw, String password) {
        String pw = password == null ? "" : password;
        String text;
        try (PDDocument doc = Loader.loadPDF(raw, pw)) {
            PDFTextStripper stripper = new PDFTextStripper();
            // Content-stream order keeps a date and an overlapping description apart.
            stripper.setSortByPosition(false);
            text = stripper.getText(doc);
        } catch (InvalidPasswordException e) {
            if (!pw.isEmpty()) {
                throw new PasswordError("That password didn't open the PDF. Try again.", "password_incorrect");
            }
            throw new PasswordError("This PDF is password-protected. Enter its password to import it.",
                    "password_required");
        } catch (IOException | RuntimeException e) {
            throw new StatementImporter.ImportError("This PDF could not be read.");
        }
        List<String> lines = List.of(text.split("\r\n|\n|\r"));
        if (lines.stream().allMatch(l -> l.strip().isEmpty())) {
            throw new StatementImporter.ImportError("No text found in this PDF (it may be a scanned image). "
                    + "Export the statement as CSV, Excel or JSON instead.");
        }
        return lines;
    }

    public static Parsed pdfRows(byte[] raw, String password) {
        return parsePdfLines(pdfTextLines(raw, password));
    }
}
